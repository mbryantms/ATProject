"""
Link extraction and management system for internal backlinks.
"""

from .extractor import (
    extract_internal_links,
    find_post_by_slug,
    update_post_links,
)

__all__ = [
    "extract_internal_links",
    "update_post_links",
    "find_post_by_slug",
]
