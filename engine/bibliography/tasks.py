"""
Celery tasks for bibliography background processing.

Includes Zotero sync and URL health checking.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=1800,
    time_limit=1860,
)
def sync_zotero_library(self, full: bool = False):
    """
    Sync sources from Zotero library.

    Schedulable via Celery Beat for periodic sync.
    """
    from engine.bibliography.zotero_sync import sync_zotero_library as do_sync

    try:
        stats = do_sync(full=full)
        logger.info("Zotero sync complete: %s", stats)
        return {"success": True, **stats}
    except Exception as e:
        logger.exception("Zotero sync failed")
        return {"success": False, "error": str(e)}


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    # Worst case per source: HEAD + GET fallback + Wayback lookup, each up to
    # the 20s resolver timeout, across a batch of 50.
    soft_time_limit=3600,
    time_limit=3660,
)
def check_source_urls_task(self, batch_size: int = 50, max_age_days: int = 7):
    """
    Check a batch of source URLs for availability.

    Schedulable via Celery Beat for daily checks.
    """
    from engine.bibliography.link_checker import check_source_urls

    try:
        stats = check_source_urls(batch_size=batch_size, max_age_days=max_age_days)
        logger.info("URL check complete: %s", stats)
        return {"success": True, **stats}
    except Exception as e:
        logger.exception("URL check failed")
        return {"success": False, "error": str(e)}


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=120,
    time_limit=180,
)
def archive_source_url(self, source_id: int):
    """
    Proactively submit a source's URL to the Wayback Machine (Save Page Now).

    Enqueued by the Source post_save signal when a source is created with a
    URL or an existing source's URL changes. Also backfills ``url_archive``
    with an existing snapshot when one is already available.
    """
    from engine.bibliography.link_checker import (
        check_wayback_machine,
        submit_to_wayback,
    )
    from engine.models import Source

    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        return {"success": False, "error": f"Source {source_id} not found"}

    if not source.url:
        return {"success": False, "error": "Source has no URL"}

    submitted = submit_to_wayback(source.url)

    # Best-effort: record an existing snapshot URL so the bibliography can
    # fall back to it if the primary URL later breaks. Save Page Now is
    # asynchronous on archive.org's side, so a just-submitted page may not
    # be available yet — the periodic link checker picks it up later.
    archive_url = ""
    if not source.url_archive:
        archive_url = check_wayback_machine(source.url) or ""
        if archive_url:
            Source.objects.filter(pk=source_id).update(url_archive=archive_url)

    logger.info(
        "Wayback archival for source %s: submitted=%s snapshot=%s",
        source_id,
        submitted,
        bool(archive_url or source.url_archive),
    )
    return {"success": True, "submitted": submitted, "archive_url": archive_url}


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def extract_source_file_text(self, source_file_id: int):
    """
    Extract full text from an archived source file for search indexing.

    Enqueued by the SourceFile post_save signal for new/replaced files.
    Updates the file row via queryset .update() (no signal loop), then
    refreshes the parent Source's search vector so library search covers
    the file content.
    """
    from engine.bibliography.text_extraction import extract_text
    from engine.models import Source, SourceFile
    from engine.models.source import source_search_vector

    try:
        source_file = SourceFile.objects.get(pk=source_file_id)
    except SourceFile.DoesNotExist:
        return {"success": False, "error": f"SourceFile {source_file_id} not found"}

    text = extract_text(source_file.file, source_file.extension)
    SourceFile.objects.filter(pk=source_file_id).update(extracted_text=text)
    Source.all_objects.filter(pk=source_file.source_id).update(
        search_vector=source_search_vector()
    )

    logger.info("Extracted %d chars from source file %s", len(text), source_file_id)
    return {"success": True, "chars": len(text)}


@shared_task(bind=True, soft_time_limit=120, time_limit=180)
def fetch_metadata_for_source(self, source_id: int, resolve_type: str = "doi"):
    """
    Fetch and apply metadata for a single source.

    Args:
        source_id: Source pk.
        resolve_type: One of "doi", "isbn", "url".
    """
    from engine.bibliography.metadata_resolvers import (
        apply_metadata_to_source,
        resolve_doi,
        resolve_isbn,
        resolve_url,
    )
    from engine.models import Source

    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        return {"success": False, "error": f"Source {source_id} not found"}

    resolver = {"doi": resolve_doi, "isbn": resolve_isbn, "url": resolve_url}
    resolve_fn = resolver.get(resolve_type)
    if not resolve_fn:
        return {"success": False, "error": f"Unknown resolve type: {resolve_type}"}

    # Get the value to resolve
    value = getattr(source, resolve_type, "") or getattr(source, "url", "")
    if not value:
        return {"success": False, "error": f"No {resolve_type} on source"}

    csl_data = resolve_fn(value)
    if not csl_data:
        return {
            "success": False,
            "error": f"No metadata found for {resolve_type}={value}",
        }

    updated = apply_metadata_to_source(source, csl_data)
    if updated:
        source.save()

    return {"success": True, "updated_fields": updated}


@shared_task(bind=True, soft_time_limit=1800, time_limit=1860)
def check_source_urls_for_ids(self, source_ids):
    """Check URL availability for a specific set of sources (admin bulk action).

    Runs off the request thread so a large selection can't time out the admin
    (each fetch can take up to the resolver timeout).
    """
    from django.utils import timezone

    from engine.bibliography.link_checker import check_url, check_wayback_machine
    from engine.models import Source

    checked = broken = 0
    for source in Source.objects.filter(pk__in=source_ids).exclude(url=""):
        result = check_url(source.url)
        status = result["status"]
        archive_url = source.url_archive
        if status == "broken":
            archive_url = check_wayback_machine(source.url) or archive_url
            if archive_url and archive_url != source.url_archive:
                status = "archived"
            broken += 1
        Source.objects.filter(pk=source.pk).update(
            url_status=status,
            url_last_checked=timezone.now(),
            url_check_count=source.url_check_count + 1,
            url_archive=archive_url,
        )
        checked += 1
    logger.info("URL check (ids) complete: checked=%s broken=%s", checked, broken)
    return {"success": True, "checked": checked, "broken": broken}


@shared_task(bind=True, soft_time_limit=900, time_limit=960)
def resync_zotero_sources(self, source_ids):
    """Re-import a specific set of sources from Zotero (admin bulk action)."""
    from engine.bibliography.zotero_sync import (
        _update_source_from_csl,
        get_zotero_client,
    )
    from engine.models import Source

    try:
        zot = get_zotero_client()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    updated = 0
    for source in Source.objects.filter(pk__in=source_ids).exclude(zotero_key=""):
        try:
            items = zot.item(source.zotero_key, format="csljson")
            if items:
                csl_item = items if isinstance(items, dict) else items[0]
                _update_source_from_csl(source, csl_item)
                source.zotero_raw = csl_item
                source.save()
                updated += 1
        except Exception:
            logger.exception("Zotero re-import failed for source %s", source.pk)
    return {"success": True, "updated": updated}
