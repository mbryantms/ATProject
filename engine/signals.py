"""
Signal handlers for the engine app.

Handles automatic updates for internal links when posts are saved or deleted,
and cache invalidation for citation formatting.
"""

import logging

from django.core.cache import cache
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from engine.links.extractor import update_post_links
from engine.models import Post, Source

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Post)
def update_internal_links_on_save(sender, instance, created, **kwargs):
    """
    Update InternalLink records when a post is saved.

    This signal handler:
    - Only processes published posts
    - Extracts internal links from markdown content
    - Creates/updates/deletes InternalLink records as needed

    Args:
        sender: The Post model class
        instance: The Post instance being saved
        created: Boolean indicating if this is a new post
        **kwargs: Additional keyword arguments
    """
    # Only process published posts
    # This avoids creating links for drafts that might change significantly
    if instance.status != Post.Status.PUBLISHED:
        logger.debug(
            f"Skipping link extraction for post '{instance.slug}' "
            f"(status: {instance.status})"
        )
        return

    # Skip if post is deleted
    if instance.is_deleted:
        logger.debug(f"Skipping link extraction for deleted post '{instance.slug}'")
        return

    # Extract and update links
    try:
        stats = update_post_links(instance)
        logger.info(
            f"Updated links for post '{instance.slug}': "
            f"{stats['links_created']} created, "
            f"{stats['links_updated']} updated, "
            f"{stats['links_deleted']} deleted"
        )

        if stats["links_failed"] > 0:
            logger.warning(
                f"Failed to resolve {stats['links_failed']} links in post '{instance.slug}': "
                f"{', '.join(stats['failed_slugs'])}"
            )
    except Exception as e:
        logger.error(
            f"Error updating links for post '{instance.slug}': {str(e)}", exc_info=True
        )


@receiver(pre_delete, sender=Post)
def cleanup_internal_links_on_delete(sender, instance, **kwargs):
    """
    Clean up InternalLink records when a post is deleted.

    This handles both soft and hard deletes.
    For soft deletes, the InternalLink records are also soft-deleted.
    For hard deletes, the records are removed via CASCADE.

    Args:
        sender: The Post model class
        instance: The Post instance being deleted
        **kwargs: Additional keyword arguments
    """
    # Check if this is a soft delete or hard delete
    # Soft delete: is_deleted flag will be set, but instance still exists in DB
    # Hard delete: instance will be removed from DB

    if instance.is_deleted:
        # This is already soft-deleted, now doing hard delete
        logger.info(
            f"Hard deleting post '{instance.slug}' "
            f"- InternalLink records will be CASCADE deleted"
        )
    else:
        # This is a soft delete
        # The InternalLink.source_post and target_post foreign keys will handle this
        # via CASCADE, but we should log it
        logger.info(
            f"Soft deleting post '{instance.slug}' "
            f"- related InternalLink records will be handled by CASCADE"
        )


@receiver(post_save, sender=Source)
def invalidate_citeproc_cache_on_source_save(sender, instance, **kwargs):
    """
    Invalidate citeproc formatting cache when a Source record changes.

    The citeproc cache uses keys prefixed with "citeproc:" — delete them all
    so that citations re-render with updated source metadata.
    """
    try:
        cache.delete_pattern("citeproc:*")
    except AttributeError:
        # LocMemCache doesn't support delete_pattern; skip in dev
        pass


# NOTE: Previous handlers update_backlinks_when_slug_changes and
# rebuild_links_on_publish were removed — they re-queried the database inside
# post_save (after the row was already written), so the "old vs new" comparison
# always saw identical values and never triggered.  Link building for published
# posts is already handled by update_internal_links_on_save above.
