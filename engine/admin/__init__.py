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

# Import Celery admin integration if available
try:
    from django.contrib import admin
    from django.contrib.admin.sites import NotRegistered
    from unfold.admin import ModelAdmin

    def _reregister_with_unfold(model, base_admin):
        """Re-register third-party admin classes with Unfold styling."""
        try:
            admin.site.unregister(model)
        except NotRegistered:
            pass

        attrs = {"__module__": __name__, "list_filter_sidebar": True}
        admin_class = type(
            f"Unfold{model.__name__}Admin", (ModelAdmin, base_admin), attrs
        )
        admin.site.register(model, admin_class)

    # Register Celery Beat models with Unfold styling
    try:
        from django_celery_beat import admin as beat_admin
        from django_celery_beat.models import (
            ClockedSchedule,
            CrontabSchedule,
            IntervalSchedule,
            PeriodicTask,
            SolarSchedule,
        )

        beat_admin_map = [
            (PeriodicTask, beat_admin.PeriodicTaskAdmin),
            (CrontabSchedule, beat_admin.CrontabScheduleAdmin),
            (IntervalSchedule, beat_admin.IntervalScheduleAdmin),
            (SolarSchedule, beat_admin.SolarScheduleAdmin),
            (ClockedSchedule, beat_admin.ClockedScheduleAdmin),
        ]
        for model, admin_class in beat_admin_map:
            _reregister_with_unfold(model, admin_class)

    except ImportError:
        # django-celery-beat is not installed
        pass

except ImportError:
    # Unfold or other dependencies not available
    pass


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
