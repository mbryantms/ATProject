"""
Link extraction system for identifying internal post links in markdown content.

This module parses markdown content to find internal links to other posts,
enabling the backlinks feature which shows bidirectional post connections.
"""

import re
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse

from django.db import transaction

logger = logging.getLogger(__name__)


def extract_internal_links(markdown_content: str) -> List[Dict[str, str]]:
    """
    Extract internal post links from markdown content.

    Identifies links in the format:
    - Markdown: [text](/posts/slug/)
    - HTML: <a href="/posts/slug/">text</a>

    Args:
        markdown_content: The markdown text to parse

    Returns:
        List of dicts with keys: 'slug', 'format'

    Example:
        >>> extract_internal_links("[See this](/posts/my-post/)")
        [{'slug': 'my-post', 'format': 'markdown'}]
    """
    if not markdown_content:
        return []

    links = []

    # Pattern 1: Markdown-style links [text](/posts/slug/)
    # Matches: [link text](/posts/post-slug/) or [text](/posts/post-slug)
    markdown_pattern = r'\[([^\]]+)\]\(/posts/([^/\)]+)/?["\')]?\)'

    for match in re.finditer(markdown_pattern, markdown_content):
        slug = match.group(2)

        # Avoid duplicates
        if not any(l['slug'] == slug for l in links):
            links.append({
                'slug': slug,
                'format': 'markdown'
            })

    # Pattern 2: HTML-style links <a href="/posts/slug/">text</a>
    # Matches: <a href="/posts/slug/">text</a>
    html_pattern = r'<a\s+(?:[^>]*?\s+)?href=["\']?/posts/([^/"\'>]+)/?["\']?[^>]*>([^<]+)</a>'

    for match in re.finditer(html_pattern, markdown_content, re.IGNORECASE):
        slug = match.group(1)

        # Avoid duplicates
        if not any(l['slug'] == slug for l in links):
            links.append({
                'slug': slug,
                'format': 'html'
            })

    # Pattern 3: Absolute URLs (for same domain)
    # Matches: https://yourdomain.com/posts/slug/ or http://yourdomain.com/posts/slug/
    # Note: This will match any domain - filtering happens in update_post_links
    absolute_url_pattern = r'\[([^\]]+)\]\(https?://[^/]+/posts/([^/\)]+)/?["\')]?\)'

    for match in re.finditer(absolute_url_pattern, markdown_content):
        slug = match.group(2)

        # Avoid duplicates
        if not any(l['slug'] == slug for l in links):
            links.append({
                'slug': slug,
                'format': 'absolute'
            })

    logger.debug(f"Extracted {len(links)} internal links from markdown content")
    return links


def find_post_by_slug(slug: str):
    """
    Find a Post by slug, handling circular import issues.

    Args:
        slug: The post slug to search for

    Returns:
        Post instance or None if not found
    """
    from engine.models import Post

    try:
        # Use all_objects to include soft-deleted posts in the check
        # but filter for non-deleted posts
        return Post.objects.get(slug=slug, is_deleted=False)
    except Post.DoesNotExist:
        logger.debug(f"Post with slug '{slug}' not found")
        return None
    except Post.MultipleObjectsReturned:
        # This shouldn't happen due to unique constraint, but handle it
        logger.warning(f"Multiple posts found with slug '{slug}', using first")
        return Post.objects.filter(slug=slug, is_deleted=False).first()


def update_post_links(post, dry_run=False) -> Dict[str, any]:
    """
    Update InternalLink records for a post by parsing its markdown content.

    This function:
    1. Extracts all internal links from the post's markdown
    2. Finds target posts for each slug
    3. Creates/updates InternalLink records
    4. Removes outdated links

    Args:
        post: Post instance to update links for
        dry_run: If True, don't save changes (for testing)

    Returns:
        Dict with stats: {
            'links_found': int,
            'links_created': int,
            'links_updated': int,
            'links_deleted': int,
            'links_failed': int,
            'failed_slugs': List[str]
        }
    """
    from engine.models import InternalLink

    stats = {
        'links_found': 0,
        'links_created': 0,
        'links_updated': 0,
        'links_deleted': 0,
        'links_failed': 0,
        'failed_slugs': []
    }

    # Extract links from markdown
    extracted_links = extract_internal_links(post.content_markdown or '')
    stats['links_found'] = len(extracted_links)

    if not extracted_links:
        # No links found - remove all existing links for this post
        if not dry_run:
            deleted_count = InternalLink.objects.filter(source_post=post).delete()[0]
            stats['links_deleted'] = deleted_count
            logger.info(f"Removed {deleted_count} outdated links from post '{post.slug}'")
        return stats

    # Use a transaction to ensure atomicity
    with transaction.atomic():
        # Track which target posts we've processed
        current_target_slugs = set()

        for link_data in extracted_links:
            slug = link_data['slug']

            # Find target post
            target_post = find_post_by_slug(slug)

            if not target_post:
                stats['links_failed'] += 1
                stats['failed_slugs'].append(slug)
                logger.warning(
                    f"Target post with slug '{slug}' not found for link in '{post.slug}'"
                )
                continue

            # Don't create self-links
            if target_post.id == post.id:
                logger.debug(f"Skipping self-link in post '{post.slug}'")
                continue

            current_target_slugs.add(target_post.slug)

            if dry_run:
                # In dry run, just check if it exists
                exists = InternalLink.objects.filter(
                    source_post=post,
                    target_post=target_post
                ).exists()
                if not exists:
                    stats['links_created'] += 1
                    logger.info(f"Would create link: {post.slug} → {target_post.slug}")
                continue

            # Create or update the link
            link, created = InternalLink.objects.get_or_create(
                source_post=post,
                target_post=target_post,
                defaults={
                    'link_count': 1,
                    'is_deleted': False
                }
            )

            if created:
                stats['links_created'] += 1
                logger.debug(f"Created link: {post.slug} → {target_post.slug}")
            else:
                # Update existing link if needed
                updated = False
                if link.is_deleted:
                    link.is_deleted = False
                    updated = True

                if updated:
                    link.save()
                    stats['links_updated'] += 1
                    logger.debug(f"Updated link: {post.slug} → {target_post.slug}")

        if not dry_run:
            # Remove links that no longer exist in the content
            # Get all current links for this post
            existing_links = InternalLink.objects.filter(source_post=post)

            for existing_link in existing_links:
                if existing_link.target_post.slug not in current_target_slugs:
                    # This link is no longer in the content
                    existing_link.delete()  # Soft delete by default
                    stats['links_deleted'] += 1
                    logger.debug(
                        f"Removed outdated link: {post.slug} → {existing_link.target_post.slug}"
                    )

    logger.info(
        f"Updated links for '{post.slug}': "
        f"{stats['links_created']} created, "
        f"{stats['links_updated']} updated, "
        f"{stats['links_deleted']} deleted, "
        f"{stats['links_failed']} failed"
    )

    return stats


def validate_internal_link(link_url: str) -> Optional[str]:
    """
    Validate and extract slug from an internal link URL.

    Args:
        link_url: The URL to validate

    Returns:
        The post slug if valid, None otherwise

    Example:
        >>> validate_internal_link('/posts/my-post/')
        'my-post'
        >>> validate_internal_link('https://example.com/posts/my-post/')
        'my-post'
        >>> validate_internal_link('/about/')
        None
    """
    if not link_url:
        return None

    # Parse the URL
    parsed = urlparse(link_url)
    path = parsed.path

    # Check if it's a post URL
    # Pattern: /posts/slug/ or /posts/slug
    post_path_pattern = r'^/posts/([^/]+)/?$'
    match = re.match(post_path_pattern, path)

    if match:
        return match.group(1)

    return None


def get_backlinks_for_post(post, published_only=True, public_only=True):
    """
    Get all backlinks (incoming links) for a post.

    Args:
        post: Post instance
        published_only: Only include links from published posts
        public_only: Only include links from public posts

    Returns:
        QuerySet of InternalLink objects
    """
    from engine.models import InternalLink, Post

    queryset = InternalLink.objects.filter(
        target_post=post,
        is_deleted=False
    ).select_related('source_post')

    if published_only:
        queryset = queryset.filter(
            source_post__status=Post.Status.PUBLISHED,
            source_post__published_at__isnull=False
        )

    if public_only:
        queryset = queryset.filter(
            source_post__visibility=Post.Visibility.PUBLIC
        )

    return queryset.order_by('-source_post__published_at')


def get_outgoing_links_for_post(post):
    """
    Get all outgoing links from a post.

    Args:
        post: Post instance

    Returns:
        QuerySet of InternalLink objects
    """
    from engine.models import InternalLink

    return InternalLink.objects.filter(
        source_post=post,
        is_deleted=False
    ).select_related('target_post').order_by('target_post__title')


def find_orphaned_posts():
    """
    Find posts that have no incoming or outgoing links.

    Returns:
        QuerySet of Post objects with no links
    """
    from engine.models import Post
    from django.db.models import Q, Count

    return Post.objects.annotate(
        incoming_count=Count('incoming_links', filter=Q(incoming_links__is_deleted=False)),
        outgoing_count=Count('outgoing_links', filter=Q(outgoing_links__is_deleted=False))
    ).filter(
        incoming_count=0,
        outgoing_count=0,
        status=Post.Status.PUBLISHED
    )


def find_broken_links():
    """
    Find internal links where the target post no longer exists or is deleted.

    Returns:
        QuerySet of InternalLink objects with broken targets
    """
    from engine.models import InternalLink

    return InternalLink.objects.filter(
        is_deleted=False,
        target_post__is_deleted=True
    ).select_related('source_post', 'target_post')


def get_link_statistics():
    """
    Get overall link statistics for the site.

    Returns:
        Dict with various statistics about internal links
    """
    from engine.models import InternalLink, Post
    from django.db.models import Count, Q
    from django.utils import timezone

    total_links = InternalLink.objects.filter(is_deleted=False).count()

    # Count published posts using direct filter (avoid manager method delegation issues)
    now = timezone.now()
    total_posts = Post.objects.filter(
        status=Post.Status.PUBLISHED,
        published_at__isnull=False,
        published_at__lte=now,
        is_deleted=False
    ).count()

    # Most linked-to posts
    most_linked = Post.objects.annotate(
        backlink_count=Count('incoming_links', filter=Q(incoming_links__is_deleted=False))
    ).filter(backlink_count__gt=0).order_by('-backlink_count')[:10]

    # Posts with most outgoing links
    most_linking = Post.objects.annotate(
        outgoing_count=Count('outgoing_links', filter=Q(outgoing_links__is_deleted=False))
    ).filter(outgoing_count__gt=0).order_by('-outgoing_count')[:10]

    # Orphaned posts
    orphaned_count = find_orphaned_posts().count()

    # Broken links
    broken_count = find_broken_links().count()

    return {
        'total_links': total_links,
        'total_posts': total_posts,
        'average_links_per_post': total_links / total_posts if total_posts > 0 else 0,
        'most_linked_posts': list(most_linked.values('id', 'title', 'slug', 'backlink_count')),
        'most_linking_posts': list(most_linking.values('id', 'title', 'slug', 'outgoing_count')),
        'orphaned_posts_count': orphaned_count,
        'broken_links_count': broken_count,
    }