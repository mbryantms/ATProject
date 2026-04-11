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


@shared_task(bind=True)
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
