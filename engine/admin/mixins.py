"""
Admin mixins for the Engine application.

This module contains reusable admin mixins that provide common functionality
across different admin classes.
"""

from django.contrib import admin, messages


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
        count = 0
        for obj in queryset:
            # Respect the model's custom delete(soft=True) if present.
            if hasattr(obj, "delete"):
                obj.delete(soft=True)
                count += 1
        self.message_user(
            request, f"Soft-deleted {count} item(s).", level=messages.SUCCESS
        )

    @admin.action(description="Restore selected (clear soft delete)")
    def restore_selected(self, request, queryset):
        count = 0
        for obj in queryset:
            if hasattr(obj, "is_deleted"):
                obj.is_deleted = False
                if hasattr(obj, "deleted_at"):
                    obj.deleted_at = None
                obj.save(
                    update_fields=(
                        ["is_deleted", "deleted_at"]
                        if hasattr(obj, "deleted_at")
                        else ["is_deleted"]
                    )
                )
                count += 1
        self.message_user(request, f"Restored {count} item(s).", level=messages.SUCCESS)
