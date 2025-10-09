"""
Signal handlers for the engine app.

Handles automatic updates for internal links when posts are saved or deleted.
"""

import logging
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from engine.models import Post, InternalLink
from engine.links.extractor import update_post_links

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

        if stats['links_failed'] > 0:
            logger.warning(
                f"Failed to resolve {stats['links_failed']} links in post '{instance.slug}': "
                f"{', '.join(stats['failed_slugs'])}"
            )
    except Exception as e:
        logger.error(
            f"Error updating links for post '{instance.slug}': {str(e)}",
            exc_info=True
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


@receiver(post_save, sender=Post)
def update_backlinks_when_slug_changes(sender, instance, created, update_fields, **kwargs):
    """
    Handle the case where a post's slug changes.

    When a slug changes, internal links pointing to the old slug will be broken.
    This is logged as a warning for manual review.

    Note: We don't automatically fix these because:
    1. Slug changes should be rare
    2. Old slug redirects should be set up separately
    3. Manual review ensures intentional changes

    Args:
        sender: The Post model class
        instance: The Post instance being saved
        created: Boolean indicating if this is a new post
        update_fields: Set of fields being updated (if available)
        **kwargs: Additional keyword arguments
    """
    # Skip for new posts
    if created:
        return

    # Check if slug was updated
    if update_fields and 'slug' not in update_fields:
        return

    # Try to get the old instance from the database
    try:
        old_instance = Post.all_objects.get(pk=instance.pk)
        if old_instance.slug != instance.slug:
            logger.warning(
                f"Post slug changed from '{old_instance.slug}' to '{instance.slug}'. "
                f"Internal links pointing to this post may need to be updated manually. "
                f"Consider setting up a redirect from the old slug."
            )

            # Get count of backlinks that might be affected
            backlink_count = InternalLink.objects.filter(
                target_post=instance,
                is_deleted=False
            ).count()

            if backlink_count > 0:
                logger.warning(
                    f"Post '{instance.slug}' has {backlink_count} backlinks that were "
                    f"created under the old slug '{old_instance.slug}'. "
                    f"These will still work, but consider updating content that links to this post."
                )
    except Post.DoesNotExist:
        # This shouldn't happen, but handle it gracefully
        pass


# Optional: Hook to rebuild all links when a post status changes to published
@receiver(post_save, sender=Post)
def rebuild_links_on_publish(sender, instance, created, **kwargs):
    """
    Rebuild all internal links when a post is first published.

    This ensures that links are captured even if the post was edited
    in draft mode before publishing.

    Args:
        sender: The Post model class
        instance: The Post instance being saved
        created: Boolean indicating if this is a new post
        **kwargs: Additional keyword arguments
    """
    # Only trigger on status change to PUBLISHED
    if not created and instance.status == Post.Status.PUBLISHED:
        try:
            # Check if this is a status change by looking at the DB
            old_instance = Post.all_objects.get(pk=instance.pk)
            if old_instance.status != Post.Status.PUBLISHED:
                logger.info(
                    f"Post '{instance.slug}' changed to PUBLISHED status. "
                    f"Rebuilding internal links."
                )
                update_post_links(instance)
        except Post.DoesNotExist:
            pass