"""
Admin mixins for the Engine application.

This module contains reusable admin mixins that provide common functionality
across different admin classes.
"""

from django.contrib import admin, messages
from django.utils import timezone


class SoftDeleteAdminMixin:
    """Show ALL objects in admin (including soft-deleted), add actions to delete/restore."""

    def get_queryset(self, request):
        # Use the 'all_objects' manager so admins can see and restore soft-deleted rows.
        qs = super().get_queryset(request)
        if hasattr(self.model, "all_objects"):
            return self.model.all_objects.get_queryset()
        return qs

    @admin.action(description="Soft delete selected")
    def soft_delete_selected(self, request, queryset):
        update_fields = {"is_deleted": True}
        if hasattr(self.model, "deleted_at"):
            update_fields["deleted_at"] = timezone.now()
        count = queryset.update(**update_fields)
        self.message_user(
            request, f"Soft-deleted {count} item(s).", level=messages.SUCCESS
        )

    @admin.action(description="Restore selected (clear soft delete)")
    def restore_selected(self, request, queryset):
        update_fields = {"is_deleted": False}
        if hasattr(self.model, "deleted_at"):
            update_fields["deleted_at"] = None
        count = queryset.update(**update_fields)
        self.message_user(request, f"Restored {count} item(s).", level=messages.SUCCESS)
