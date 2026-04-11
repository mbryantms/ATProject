"""
Zotero integration for the bibliography system.

Uses pyzotero to import and incrementally sync sources from a Zotero library.
Zotero items are mapped to the universal Source model — no separate Zotero-specific model.
"""

import logging

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


def sync_zotero_library(full: bool = False, dry_run: bool = False) -> dict:
    """
    Sync sources from a Zotero library.

    Args:
        full: If True, re-import all items. If False, only fetch items
              modified since the last sync version.
        dry_run: If True, don't save changes.

    Returns:
        Stats dict with created, updated, skipped, errors counts.
    """
    from engine.models import SiteSettings, Source

    settings = SiteSettings.load()
    zot = get_zotero_client()

    stats = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
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

    # Fetch items from Zotero in CSL-JSON format.
    # NOTE: pyzotero's everything() breaks with format='csljson' because
    # csljson returns a dict {"items": [...]}, and everything() tries to
    # extend() it (iterating over dict keys, not items). We paginate manually.
    try:
        items = []
        result = zot.items(**kwargs)
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

    logger.info("Fetched %d items from Zotero", len(items))

    # Get existing keys for collision avoidance
    existing_keys = set(Source.all_objects.values_list("citation_key", flat=True))

    for item in items:
        try:
            _process_zotero_item(item, existing_keys, stats, dry_run)
        except Exception as e:
            stats["errors"] += 1
            item_id = item.get("id", "unknown")
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
) -> None:
    """Process a single Zotero CSL-JSON item into a Source record."""
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
            return

        _update_source_from_csl(existing, csl_item)
        existing.zotero_raw = csl_item
        existing.save()
        stats["updated"] += 1
    else:
        # Create new source
        if dry_run:
            stats["created"] += 1
            return

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
