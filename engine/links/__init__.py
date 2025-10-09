"""
Link extraction and management system for internal backlinks.
"""

from .extractor import (
    extract_internal_links,
    update_post_links,
    find_post_by_slug,
)

__all__ = [
    'extract_internal_links',
    'update_post_links',
    'find_post_by_slug',
]