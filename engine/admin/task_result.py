"""
Custom admin configuration for Celery Task Results.

Overrides the default django_celery_results admin to provide
human-readable task names and improved display.
"""

from django.contrib import admin
from django.utils.html import format_html
from django_celery_results.admin import TaskResultAdmin as BaseTaskResultAdmin
from django_celery_results.models import TaskResult

# Human-readable task name mappings
TASK_NAME_DISPLAY = {
    # Engine tasks
    "engine.tasks.update_post_derived_content": "Update Post Content",
    "engine.tasks.extract_metadata_async": "Extract Asset Metadata",
    "engine.tasks.generate_renditions_async": "Generate Image Renditions",
    "engine.tasks.bulk_extract_metadata": "Bulk Extract Metadata",
    "engine.tasks.bulk_generate_renditions": "Bulk Generate Renditions",
    "engine.tasks.rebuild_search_vectors": "Rebuild Search Vectors",
    "engine.tasks.slow_add": "Test: Slow Add",
    # Celery built-in tasks
    "celery.backend_cleanup": "Cleanup Old Results",
}

# Status display with colors
STATUS_COLORS = {
    "SUCCESS": "#28a745",  # Green
    "FAILURE": "#dc3545",  # Red
    "PENDING": "#ffc107",  # Yellow
    "STARTED": "#17a2b8",  # Cyan
    "RETRY": "#fd7e14",    # Orange
    "REVOKED": "#6c757d",  # Gray
}


class TaskResultAdmin(BaseTaskResultAdmin):
    """
    Enhanced TaskResult admin with human-readable task names.
    """

    list_display = (
        "short_task_id",
        "task_display_name",
        "colored_status",
        "date_done",
        "duration",
        "worker",
    )
    list_filter = ("status", "date_done", "task_name", "worker")
    search_fields = ("task_name", "task_id", "status", "task_args", "task_kwargs")
    ordering = ("-date_done",)

    @admin.display(description="Task ID", ordering="task_id")
    def short_task_id(self, obj):
        """Display a shortened task ID with link to detail."""
        short_id = obj.task_id[:8] if obj.task_id else "-"
        return format_html(
            '<span title="{}">{}</span>',
            obj.task_id,
            short_id,
        )

    @admin.display(description="Task", ordering="task_name")
    def task_display_name(self, obj):
        """Display human-readable task name."""
        display_name = TASK_NAME_DISPLAY.get(obj.task_name, obj.task_name)
        # If no mapping found, try to create a readable name from the task path
        if display_name == obj.task_name and obj.task_name:
            # Extract the function name and convert to title case
            parts = obj.task_name.split(".")
            if parts:
                func_name = parts[-1]
                # Convert snake_case to Title Case
                display_name = func_name.replace("_", " ").title()
        return display_name

    @admin.display(description="Status", ordering="status")
    def colored_status(self, obj):
        """Display status with color coding."""
        color = STATUS_COLORS.get(obj.status, "#6c757d")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.status,
        )

    @admin.display(description="Duration")
    def duration(self, obj):
        """Display task duration if available."""
        if obj.date_started and obj.date_done:
            delta = obj.date_done - obj.date_started
            seconds = delta.total_seconds()
            if seconds < 1:
                return f"{seconds * 1000:.0f}ms"
            elif seconds < 60:
                return f"{seconds:.1f}s"
            else:
                minutes = int(seconds // 60)
                secs = int(seconds % 60)
                return f"{minutes}m {secs}s"
        return "-"


# Unregister the default admin and register our custom one
admin.site.unregister(TaskResult)
admin.site.register(TaskResult, TaskResultAdmin)
