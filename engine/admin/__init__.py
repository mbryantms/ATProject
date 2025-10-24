"""
Django admin configuration for the Engine application.

This package contains modular admin classes organized by functionality:
- mixins: Shared admin mixins (soft delete functionality)
- taxonomy: Tag, TagAlias, Category, and Series admins
- post: Post and InternalLink admins with backlinks
- asset: Asset management admins (Asset, Metadata, Renditions, Folders, Tags, Collections)

All admin classes are automatically registered via @admin.register() decorators
in their respective modules.
"""

from django.conf import settings
from django.contrib import admin

# Customize admin site
admin.site.site_header = getattr(settings, 'ADMIN_SITE_HEADER', 'Django Administration')
admin.site.site_title = getattr(settings, 'ADMIN_SITE_TITLE', 'Django site admin')
admin.site.index_title = getattr(settings, 'ADMIN_INDEX_TITLE', 'Site administration')

# Import admin classes to ensure they're registered
# The @admin.register() decorators in each module handle the registration

from .asset import (
    AssetAdmin,
    AssetCollectionAdmin,
    AssetFolderAdmin,
    AssetMetadataAdmin,
    AssetRenditionAdmin,
    AssetTagAdmin,
)
from .mixins import SoftDeleteAdminMixin
from .post import InternalLinkAdmin, PostAdmin
from .taxonomy import CategoryAdmin, SeriesAdmin, TagAdmin, TagAliasAdmin

# Export all admin classes for convenient imports
__all__ = [
    # Mixins
    "SoftDeleteAdminMixin",
    # Taxonomy
    "TagAdmin",
    "TagAliasAdmin",
    "CategoryAdmin",
    "SeriesAdmin",
    # Post
    "PostAdmin",
    "InternalLinkAdmin",
    # Asset
    "AssetAdmin",
    "AssetMetadataAdmin",
    "AssetRenditionAdmin",
    "AssetFolderAdmin",
    "AssetTagAdmin",
    "AssetCollectionAdmin",
]
