"""
Zotero integration for the bibliography system.

Uses pyzotero to import and incrementally sync sources from a Zotero library.
Zotero items are mapped to the universal Source model — no separate Zotero-specific model.

Zotero item hierarchy:
- **Top-level items**: actual sources (articles, books, etc.) — these become Sources.
- **Child items**: attachments (PDFs, snapshots) and notes — these are NOT separate Sources.
  PDFs are optionally downloaded and stored as the parent Source's archived_file.

We use zot.top() to fetch only top-level items, not zot.items() which returns everything.
"""

import hashlib
import logging

from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_zotero_client():
    """Create a pyzotero client from SiteSettings configuration."""
    from pyzotero import zotero

    from engine.models import SiteSettings

    settings = SiteSettings.load()
    if not settings.zotero_library_id or not settings.zotero_api_key:
        raise ValueError(
            "Zotero is not configured. Set library ID and API key in Site Settings."
        )

    return zotero.Zotero(
        settings.zotero_library_id,
        settings.zotero_library_type or "user",
        settings.zotero_api_key,
    )


def sync_zotero_library(
    full: bool = False,
    dry_run: bool = False,
    download_attachments: bool = True,
) -> dict:
    """
    Sync sources from a Zotero library.

    Only imports top-level items (actual sources). Child items like PDF
    attachments and notes are handled separately — PDFs are downloaded
    and stored on the parent Source's archived_file field.

    Args:
        full: If True, re-import all items. If False, only fetch items
              modified since the last sync version.
        dry_run: If True, don't save changes.
        download_attachments: If True, download PDF attachments from Zotero.

    Returns:
        Stats dict with created, updated, skipped, errors, attachments counts.
    """
    from engine.models import SiteSettings, Source

    settings = SiteSettings.load()
    zot = get_zotero_client()

    stats = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "attachments_downloaded": 0,
        "error_details": [],
    }

    # Determine what to fetch
    kwargs = {"format": "csljson"}
    if not full and settings.zotero_last_sync_version > 0:
        kwargs["since"] = settings.zotero_last_sync_version
        logger.info(
            "Incremental sync: fetching items since version %d",
            settings.zotero_last_sync_version,
        )
    else:
        logger.info("Full sync: fetching all items")

    # Fetch ONLY top-level items in CSL-JSON format.
    # zot.top() excludes child items (attachments, notes) so each Zotero
    # entry becomes exactly one Source.
    #
    # NOTE: pyzotero's everything() breaks with format='csljson' because
    # csljson returns {"items": [...]}, and everything() iterates dict keys.
    # We paginate manually instead.
    try:
        items = []
        result = zot.top(**kwargs)
        if isinstance(result, dict):
            items.extend(result.get("items", []))
        else:
            items.extend(result)

        while zot.links.get("next"):
            result = zot.follow()
            if isinstance(result, dict):
                items.extend(result.get("items", []))
            else:
                items.extend(result)
    except Exception as e:
        logger.exception("Failed to fetch items from Zotero")
        stats["errors"] += 1
        stats["error_details"].append(f"Fetch failed: {e}")
        return stats

    logger.info("Fetched %d top-level items from Zotero", len(items))

    # Get existing keys for collision avoidance
    existing_keys = set(Source.all_objects.values_list("citation_key", flat=True))

    for item in items:
        try:
            source = _process_zotero_item(item, existing_keys, stats, dry_run)

            # Download PDF attachments for this source
            if source and download_attachments and not dry_run:
                _download_attachments(zot, source, stats)

        except Exception as e:
            stats["errors"] += 1
            item_id = item.get("id", "unknown") if isinstance(item, dict) else "unknown"
            stats["error_details"].append(f"Item {item_id}: {e}")
            logger.exception("Error processing Zotero item %s", item_id)

    # Update sync version
    if not dry_run and stats["errors"] == 0:
        try:
            new_version = zot.last_modified_version()
            SiteSettings.objects.filter(pk=1).update(
                zotero_last_sync_version=new_version,
                zotero_last_sync_at=timezone.now(),
            )
        except Exception:
            logger.exception("Failed to update sync version")

    return stats


def _process_zotero_item(
    csl_item: dict,
    existing_keys: set,
    stats: dict,
    dry_run: bool,
):
    """
    Process a single Zotero CSL-JSON item into a Source record.

    Returns the Source instance (for attachment downloading), or None.
    """
    from engine.bibliography.citation_keys import (
        generate_citation_key,
        resolve_collision,
    )
    from engine.models import Source

    item_id = csl_item.get("id", "")

    # Check if we already have this Zotero item
    zotero_key = str(item_id)
    existing = Source.all_objects.filter(zotero_key=zotero_key).first()

    if existing:
        # Update existing source (but never overwrite citation_key)
        if dry_run:
            stats["updated"] += 1
            return None

        _update_source_from_csl(existing, csl_item)
        existing.zotero_raw = csl_item
        existing.save()
        stats["updated"] += 1
        return existing
    else:
        # Create new source
        if dry_run:
            stats["created"] += 1
            return None

        source = Source()
        _update_source_from_csl(source, csl_item)
        source.zotero_key = zotero_key
        source.zotero_raw = csl_item

        # Generate citation key
        base_key = generate_citation_key(
            authors=source.authors or [],
            issued_date=source.issued_date,
            title=source.title or "",
        )
        source.citation_key = resolve_collision(base_key, existing_keys)
        existing_keys.add(source.citation_key)

        source.save()
        stats["created"] += 1
        return source


def _download_attachments(zot, source, stats: dict) -> None:
    """
    Download PDF attachments from Zotero for a source.

    Checks child items of the Zotero item for PDF attachments. If found,
    downloads the first PDF and stores it as the source's archived_file.
    Skips if the source already has an archived file.
    """
    if source.archived_file:
        return  # Already has a file

    if not source.zotero_key:
        return

    try:
        children = zot.children(source.zotero_key)
    except Exception:
        logger.debug("Could not fetch children for Zotero item %s", source.zotero_key)
        return

    for child in children:
        data = child.get("data", {})
        content_type = data.get("contentType", "")
        item_type = data.get("itemType", "")

        # Only download PDF attachments (not snapshots, notes, links)
        if item_type != "attachment" or content_type != "application/pdf":
            continue

        child_key = child.get("key", "")
        if not child_key:
            continue

        try:
            # pyzotero's file() returns the raw file content as bytes
            pdf_content = zot.file(child_key)
            if not pdf_content:
                continue

            # Compute SHA-256 for deduplication
            file_hash = hashlib.sha256(pdf_content).hexdigest()

            # Check for duplicate
            from engine.models import Source as SourceModel

            if (
                SourceModel.all_objects.filter(archived_file_hash=file_hash)
                .exclude(pk=source.pk)
                .exists()
            ):
                logger.info(
                    "Skipping duplicate file (hash %s) for %s",
                    file_hash[:12],
                    source.citation_key,
                )
                continue

            # Build a filename
            filename = data.get("filename", f"{source.citation_key}.pdf")
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"

            # Save to the source's archived_file field
            source.archived_file.save(filename, ContentFile(pdf_content), save=False)
            source.archived_file_hash = file_hash
            source.save(
                update_fields=["archived_file", "archived_file_hash", "updated_at"]
            )

            stats["attachments_downloaded"] += 1
            logger.info(
                "Downloaded PDF for %s (%s, %d bytes)",
                source.citation_key,
                filename,
                len(pdf_content),
            )

            # Only download the first PDF per source
            break

        except Exception:
            logger.debug(
                "Could not download attachment %s for %s",
                child_key,
                source.citation_key,
            )


def _update_source_from_csl(source, csl_item: dict) -> None:
    """Map CSL-JSON fields onto a Source instance."""
    source.title = csl_item.get("title", "") or ""
    source.source_type = csl_item.get("type", "document")
    source.authors = csl_item.get("author", [])
    source.editors = csl_item.get("editor", [])
    source.translators = csl_item.get("translator", [])
    source.container_title = csl_item.get("container-title", "")
    source.publisher = csl_item.get("publisher", "")
    source.publisher_place = csl_item.get("publisher-place", "")
    source.volume = csl_item.get("volume", "")
    source.issue = csl_item.get("issue", "")
    source.page = csl_item.get("page", "")
    source.edition = csl_item.get("edition", "")
    source.issued_date = csl_item.get("issued")
    source.accessed_date = csl_item.get("accessed")
    source.doi = csl_item.get("DOI", "")
    source.isbn = csl_item.get("ISBN", "")
    source.issn = csl_item.get("ISSN", "")
    source.url = csl_item.get("URL", "")
    source.abstract = csl_item.get("abstract", "")
    source.language = csl_item.get("language", "en")
    source.note = csl_item.get("note", "")
    source.csl_json = csl_item
