"""
Admin classes for Asset models and related components.

This module contains admin configurations for the asset management system, including:
- Asset (main asset model)
- AssetMetadata (extended EXIF, audio, document metadata)
- AssetRendition (responsive image/video versions)
- AssetFolder (hierarchical folder organization)
- AssetTag (asset tagging system)
- AssetCollection (curated asset collections)
"""

import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html



from engine.models import (
    Asset,
    AssetCollection,
    AssetFolder,
    AssetMetadata,
    AssetRendition,
    AssetTag,
)

from .mixins import SoftDeleteAdminMixin


# --------------------------
# Inline classes
# --------------------------
class AssetMetadataInline(admin.StackedInline):
    """Inline for extended asset metadata (OneToOne relationship)."""

    model = AssetMetadata
    can_delete = False
    verbose_name = "Extended Metadata"
    verbose_name_plural = "Extended Metadata"

    # Unfold-specific options for better display
    tab = True
    hide_title = True

    fieldsets = [
        (
            "Camera & Photo Information",
            {
                "fields": (
                    ("camera_make", "camera_model"),
                    "lens",
                    ("focal_length", "aperture"),
                    ("shutter_speed", "iso"),
                    "captured_at",
                ),
            },
        ),
        (
            "Location Data (GPS)",
            {
                "fields": (
                    ("latitude", "longitude"),
                    "location_name",
                    "gps_map_display",
                ),
            },
        ),
        (
            "Audio Metadata",
            {
                "fields": (
                    ("artist", "album"),
                    ("genre", "year"),
                    "track_number",
                ),
            },
        ),
        (
            "Document Metadata",
            {
                "fields": (
                    "author",
                    "subject",
                    "keywords",
                    "page_count",
                ),
            },
        ),
        (
            "Color Information",
            {
                "fields": (
                    "color_preview_display",
                    ("average_color", "color_space"),
                    "color_profile",
                    "dominant_colors",
                    "color_palette",
                ),
            },
        ),
        (
            "Image Quality",
            {
                "fields": (("dpi", "has_alpha"),),
            },
        ),
        (
            "Raw Data",
            {
                "fields": (
                    "exif_data",
                    "custom_fields",
                ),
                "classes": ["collapse"],
            },
        ),
    ]

    readonly_fields = ("gps_map_display", "color_preview_display")

    @admin.display(description="GPS Location")
    def gps_map_display(self, obj):
        """Display GPS coordinates with map link."""
        if not obj.has_gps:
            return format_html('<em style="color: #999;">No GPS data available</em>')

        # Google Maps link
        maps_url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"

        return format_html(
            '<div style="padding: 8px; background: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">'
            '<div style="font-family: monospace; margin-bottom: 4px;">📍 {:.6f}, {:.6f}</div>'
            '<a href="{}" target="_blank" style="color: #007bff; text-decoration: none;">🗺️ View on Google Maps</a>'
            "</div>",
            obj.latitude,
            obj.longitude,
            maps_url,
        )

    @admin.display(description="Color Preview")
    def color_preview_display(self, obj):
        """Display visual color preview."""
        if not obj.average_color and not obj.dominant_colors:
            return format_html('<em style="color: #999;">No color data available</em>')

        html_parts = []

        # Average color swatch
        if obj.average_color:
            html_parts.append(
                f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">'
                f'<div style="width: 40px; height: 40px; background: {obj.average_color}; border-radius: 4px; '
                f'border: 1px solid #dee2e6; box-shadow: 0 1px 3px rgba(0,0,0,0.1);"></div>'
                f"<div><strong>Average:</strong> <code>{obj.average_color}</code></div>"
                f"</div>"
            )

        # Dominant colors palette
        if obj.dominant_colors and isinstance(obj.dominant_colors, list):
            swatches = []
            for color in obj.dominant_colors[:8]:  # Show up to 8 colors
                if isinstance(color, str) and color.startswith("#"):
                    swatches.append(
                        f'<div style="width: 30px; height: 30px; background: {color}; border-radius: 3px; '
                        f'border: 1px solid #dee2e6;" title="{color}"></div>'
                    )

            if swatches:
                html_parts.append(
                    f'<div style="margin-top: 8px;">'
                    f'<div style="font-weight: 500; margin-bottom: 4px;">Dominant Colors:</div>'
                    f'<div style="display: flex; gap: 4px; flex-wrap: wrap;">{"".join(swatches)}</div>'
                    f"</div>"
                )

        return format_html(
            "".join(html_parts)
            if html_parts
            else '<em style="color: #999;">No color preview available</em>'
        )


class AssetRenditionInline(admin.TabularInline):
    """Inline for asset renditions."""

    model = AssetRendition
    extra = 0
    max_num = 20
    fields = (
        "rendition_preview",
        "width",
        "height",
        "format",
        "quality",
        "preset",
        "file_size_display",
        "status",
    )
    readonly_fields = ("rendition_preview", "file_size_display")
    ordering = ["width"]

    @admin.display(description="Preview")
    def rendition_preview(self, obj):
        """Show thumbnail of rendition."""
        if obj.file:
            return format_html(
                '<img src="{}" style="max-width: 80px; max-height: 60px; border-radius: 4px;" />',
                obj.file.url,
            )
        return "-"

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        return obj.human_file_size


# --------------------------
# Asset Admin
# --------------------------
@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin, SoftDeleteAdminMixin):
    # Add custom button to changelist
    change_list_template = "admin/engine/asset_changelist.html"

    # Compressed list view with expandable details
    list_display = [
        "asset_title_with_preview",
        "asset_type_badge",
        "key_display",
        "folder_badge",
        "collection_badge",
        "status_badge",
        "file_info_compact",
        "usage_indicator",
        "markdown_key_compact",
    ]

    # Make the title column expandable
    list_display_links = ["asset_title_with_preview"]

    list_filter = [
        "asset_type",
        "status",
        "asset_folder",
        "asset_tags",
        "is_public",
        "created_at",
        "is_deleted",
        "uploaded_by",
        "last_accessed",
    ]

    search_fields = [
        "key",
        "title",
        "description",
        "alt_text",
        "caption",
        "credit",
        "asset_folder__name",
        "asset_folder__path",
        "asset_tags__name",
    ]

    # Enable autocomplete for asset selection in PostAsset inline
    autocomplete_fields = ["uploaded_by", "asset_folder"]
    filter_horizontal = ["asset_tags"]

    def get_search_results(self, request, queryset, search_term):
        """
        Customize autocomplete search results to always show key in format: 'title (key)'
        This ensures the markdown reference display JavaScript can extract the key.
        """
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        return queryset, may_have_duplicates

    # Performance optimization
    list_select_related = ["uploaded_by"]
    list_per_page = 50

    # Show facet counts in filters (unfold feature)
    show_facets = admin.ShowFacets.ALWAYS

    readonly_fields = [
        "preview_large",
        "key_preview",
        "metadata_status_detailed",
        "markdown_reference_copyable",
        "markdown_usage_examples",
        "usage_count",
        "usage_list",
        "file_hash",
        "file_extension",
        "mime_type",
        "original_filename",
        "created_at",
        "updated_at",
        "deleted_at",
        "last_accessed",
    ]

    fieldsets = [
        (
            "Asset Details",
            {
                "fields": [
                    "preview_large",
                    ("title", "status"),
                    ("asset_type",),
                    "file",
                    ("key", "key_preview"),
                ],
                "classes": [],
                "description": "Core asset information and file upload. Leave 'Key' blank for auto-generation with smart prefixes.",
            },
        ),
        (
            "Content & Accessibility",
            {
                "fields": [
                    "alt_text",
                    "caption",
                    "description",
                ],
                "classes": [],
            },
        ),
        (
            "Attribution & Licensing",
            {
                "fields": [
                    ("credit", "license"),
                    "source_url",
                ],
                "classes": ["collapse", "unfold-column-2"],
            },
        ),
        (
            "File Metadata",
            {
                "fields": [
                    "metadata_status_detailed",
                    ("file_size", "file_extension", "mime_type"),
                    ("width", "height"),
                    ("duration", "bitrate", "frame_rate"),
                    ("original_filename", "file_hash"),
                ],
                "classes": ["collapse", "unfold-column-3"],
                "description": "Metadata is auto-populated on upload. Use 'Populate metadata' admin action to refresh.",
            },
        ),
        (
            "Image Settings",
            {
                "fields": [
                    ("focal_point_x", "focal_point_y"),
                ],
                "classes": ["collapse", "unfold-column-2"],
                "description": "Focal point coordinates (0.0-1.0) for smart cropping",
            },
        ),
        (
            "Organization & Permissions",
            {
                "fields": [
                    "asset_tags",
                    "asset_folder",
                    ("is_public", "uploaded_by"),
                    "permissions",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Markdown Integration",
            {
                "fields": [
                    "markdown_reference_copyable",
                    "markdown_usage_examples",
                ],
                "description": "Use these references in your markdown content",
            },
        ),
        (
            "Usage & Analytics",
            {
                "fields": [
                    ("usage_count", "view_count", "download_count"),
                    "last_accessed",
                    "usage_list",
                ],
                "classes": ["collapse", "unfold-column-3"],
            },
        ),
        (
            "System",
            {
                "fields": [
                    ("created_at", "updated_at"),
                    ("is_deleted", "deleted_at"),
                ],
                "classes": ["collapse", "unfold-column-2"],
            },
        ),
    ]

    inlines = [AssetMetadataInline, AssetRenditionInline]

    actions = [
        "extract_extended_metadata",
        "extract_metadata_async_action",
        "generate_renditions",
        "update_usage_count",
        "regenerate_keys",
        "mark_as_ready",
        "mark_as_archived",
        "export_metadata_csv",
        "cleanup_orphaned_renditions",
        "cleanup_unused_assets",
        "soft_delete_selected",
        "restore_selected",
    ]

    def get_queryset(self, request):
        """Optimize queryset for list view."""
        qs = super().get_queryset(request)
        # Prefetch related objects to avoid N+1 queries
        qs = qs.prefetch_related("asset_tags", "asset_folder")
        return qs

    def get_form(self, request, obj=None, **kwargs):
        """Customize form to make key field optional and add help text."""
        form = super().get_form(request, obj, **kwargs)
        if "key" in form.base_fields:
            form.base_fields["key"].required = False
            form.base_fields["key"].help_text = (
                "Leave blank for automatic generation with smart prefixes (collection/type-title). "
                "Or enter a custom key (lowercase, hyphens only)."
            )
        return form

    def get_urls(self):
        """Add custom URLs for presigned upload and cleanup views."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "presigned-upload/",
                self.admin_site.admin_view(self.presigned_upload_view),
                name="engine_asset_presigned_upload",
            ),
            path(
                "cleanup/",
                self.admin_site.admin_view(self.cleanup_view),
                name="engine_asset_cleanup",
            ),
        ]
        return custom_urls + urls

    def presigned_upload_view(self, request):
        """Custom view for large file uploads using presigned URLs."""
        context = {
            **self.admin_site.each_context(request),
            "title": "Upload Large File",
            "folders": AssetFolder.objects.all().order_by("path"),
            "tags": AssetTag.objects.all().order_by("name"),
            "opts": self.model._meta,
        }
        return render(request, "admin/engine/asset_presigned_upload.html", context)

    def cleanup_view(self, request):
        """Custom view for asset cleanup with preview and execution."""
        from datetime import timedelta

        from django.db.models import Count
        from django.utils import timezone

        context = {
            **self.admin_site.each_context(request),
            "title": "Asset Cleanup",
            "opts": self.model._meta,
        }

        # Calculate current stats
        orphaned_renditions = AssetRendition.objects.filter(asset__is_deleted=True)
        soft_deleted_assets = Asset.all_objects.filter(is_deleted=True)
        unused_assets = soft_deleted_assets.annotate(
            post_count=Count("postasset")
        ).filter(post_count=0)

        total_size = sum(a.file_size or 0 for a in unused_assets)
        total_size += sum(r.file_size or 0 for r in orphaned_renditions)

        context["stats"] = {
            "orphaned_renditions": orphaned_renditions.count(),
            "unused_assets": unused_assets.count(),
            "soft_deleted": soft_deleted_assets.count(),
            "total_size": self._format_size(total_size),
        }

        # Handle form submission
        if request.method == "POST":
            action = request.POST.get("action")
            cleanup_renditions = request.POST.get("cleanup_renditions") == "on"
            cleanup_unused = request.POST.get("cleanup_unused") == "on"
            delete_files = request.POST.get("delete_files") == "on"
            days_old = int(request.POST.get("days_old", 30))
            run_async = request.POST.get("run_async") == "on"

            cutoff_date = timezone.now() - timedelta(days=days_old)

            if action == "preview":
                # Preview mode - show what would be deleted
                preview = {
                    "orphaned_renditions": {"count": 0, "examples": []},
                    "unused_assets": {"count": 0, "examples": []},
                    "total_size": "0 B",
                }

                if cleanup_renditions:
                    qs = AssetRendition.objects.filter(
                        asset__is_deleted=True,
                        created_at__lt=cutoff_date,
                    )
                    preview["orphaned_renditions"]["count"] = qs.count()
                    preview["orphaned_renditions"]["examples"] = [
                        {
                            "width": r.width,
                            "format": r.format,
                            "asset_key": r.asset.key if r.asset else "N/A",
                        }
                        for r in qs[:5]
                    ]

                if cleanup_unused:
                    qs = (
                        Asset.all_objects.filter(
                            is_deleted=True,
                            created_at__lt=cutoff_date,
                        )
                        .annotate(post_count=Count("postasset"))
                        .filter(post_count=0)
                    )
                    preview["unused_assets"]["count"] = qs.count()
                    preview["unused_assets"]["examples"] = [
                        {
                            "key": a.key,
                            "asset_type": a.asset_type,
                            "file_size": a.human_file_size,
                        }
                        for a in qs[:5]
                    ]

                # Calculate total size
                size = 0
                if cleanup_renditions:
                    size += sum(
                        r.file_size or 0
                        for r in AssetRendition.objects.filter(
                            asset__is_deleted=True, created_at__lt=cutoff_date
                        )
                    )
                if cleanup_unused:
                    size += sum(
                        a.file_size or 0
                        for a in Asset.all_objects.filter(
                            is_deleted=True, created_at__lt=cutoff_date
                        )
                        .annotate(post_count=Count("postasset"))
                        .filter(post_count=0)
                    )
                preview["total_size"] = self._format_size(size)

                context["preview_results"] = preview

            elif action == "cleanup":
                if run_async:
                    # Run via Celery
                    try:
                        from engine.tasks import cleanup_orphaned_assets

                        result = cleanup_orphaned_assets.delay(
                            delete_files=delete_files,
                            include_soft_deleted=True,
                            days_old=days_old,
                            cleanup_renditions=cleanup_renditions,
                            cleanup_unused=cleanup_unused,
                        )
                        context["cleanup_results"] = {
                            "task_id": result.id,
                        }
                        messages.success(
                            request,
                            f"Cleanup task queued. Task ID: {result.id}",
                        )
                    except Exception as e:
                        messages.error(request, f"Failed to queue task: {e}")
                else:
                    # Run synchronously
                    results = self._run_cleanup_sync(
                        delete_files=delete_files,
                        days_old=days_old,
                        cleanup_renditions=cleanup_renditions,
                        cleanup_unused=cleanup_unused,
                    )
                    context["cleanup_results"] = results
                    messages.success(
                        request,
                        f"Cleanup complete. Freed {results['total_size_freed_human']}.",
                    )

        return render(request, "admin/engine/asset_cleanup.html", context)

    def _run_cleanup_sync(
        self, delete_files, days_old, cleanup_renditions, cleanup_unused
    ):
        """Run cleanup synchronously (for small cleanups or when Celery unavailable)."""
        from datetime import timedelta

        from django.db.models import Count
        from django.utils import timezone

        results = {
            "orphaned_renditions": {"found": 0, "deleted": 0, "files_deleted": 0},
            "unused_assets": {"found": 0, "deleted": 0, "files_deleted": 0},
            "total_size_freed": 0,
            "errors": [],
        }

        cutoff_date = timezone.now() - timedelta(days=days_old)

        if cleanup_renditions:
            orphaned = AssetRendition.objects.filter(
                asset__is_deleted=True,
                created_at__lt=cutoff_date,
            )
            results["orphaned_renditions"]["found"] = orphaned.count()
            results["total_size_freed"] += sum(r.file_size or 0 for r in orphaned)

            if delete_files:
                for r in orphaned:
                    if r.file:
                        try:
                            r.file.delete(save=False)
                            results["orphaned_renditions"]["files_deleted"] += 1
                        except Exception as e:
                            results["errors"].append(str(e))

            deleted, _ = orphaned.delete()
            results["orphaned_renditions"]["deleted"] = deleted

        if cleanup_unused:
            unused = (
                Asset.all_objects.filter(is_deleted=True, created_at__lt=cutoff_date)
                .annotate(post_count=Count("postasset"))
                .filter(post_count=0)
            )
            results["unused_assets"]["found"] = unused.count()
            results["total_size_freed"] += sum(a.file_size or 0 for a in unused)

            if delete_files:
                for a in unused:
                    for r in a.renditions.all():
                        if r.file:
                            try:
                                r.file.delete(save=False)
                            except Exception as e:
                                results["errors"].append(str(e))
                    if a.file:
                        try:
                            a.file.delete(save=False)
                            results["unused_assets"]["files_deleted"] += 1
                        except Exception as e:
                            results["errors"].append(str(e))

            deleted, _ = unused.delete()
            results["unused_assets"]["deleted"] = deleted

        results["total_size_freed_human"] = self._format_size(
            results["total_size_freed"]
        )
        return results

    @admin.display(description="Asset", ordering="title")
    def asset_title_with_preview(self, obj):
        """Combined preview thumbnail with title for compact list view."""
        icon_map = {
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "document": "📄",
            "archive": "📦",
            "other": "📎",
        }
        icon = icon_map.get(obj.asset_type, "📎")

        if obj.asset_type == "image" and obj.file:
            return format_html(
                '<div style="display: flex; align-items: center; gap: 12px;">'
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 6px; '
                'box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e9ecef;" />'
                "<div>"
                '<div style="font-weight: 500; color: #212529;">{}</div>'
                '<div style="font-size: 11px; color: #6c757d; margin-top: 2px;">{} × {}</div>'
                "</div>"
                "</div>",
                obj.file.url,
                obj.title,
                obj.width or "?",
                obj.height or "?",
            )
        else:
            return format_html(
                '<div style="display: flex; align-items: center; gap: 12px;">'
                '<div style="width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; '
                'background: #f8f9fa; border-radius: 6px; font-size: 24px; border: 1px solid #e9ecef;">{}</div>'
                '<div style="font-weight: 500; color: #212529;">{}</div>'
                "</div>",
                icon,
                obj.title,
            )

    @admin.display(description="Key", ordering="key")
    def key_display(self, obj):
        """Display key in compact format."""
        return format_html(
            '<code style="font-size: 11px; color: #495057; background: #f8f9fa; '
            'padding: 3px 6px; border-radius: 3px; font-family: monospace;">{}</code>',
            obj.key,
        )

    @admin.display(description="File Info")
    def file_info_compact(self, obj):
        """Compact file information."""
        info = []

        if obj.human_file_size:
            info.append(obj.human_file_size)

        if obj.asset_type in ["image", "video"] and obj.width and obj.height:
            info.append(f"{obj.width}×{obj.height}")

        if obj.asset_type in ["video", "audio"] and obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            if minutes > 0:
                info.append(f"{minutes}m{seconds}s")
            else:
                info.append(f"{seconds}s")

        return format_html(
            '<span style="font-size: 11px; color: #6c757d;">{}</span>',
            " • ".join(info) if info else "—",
        )

    @admin.display(description="📋")
    def markdown_key_compact(self, obj):
        """Compact markdown copy button."""
        return format_html(
            "<button type='button' "
            "onclick=\"navigator.clipboard.writeText('@asset:{}').then(() => {{ "
            "this.textContent = '✓'; "
            "setTimeout(() => {{ this.textContent = '📋'; }}, 1500); "
            '}}); event.stopPropagation();" '
            "style='background: transparent; border: 1px solid #dee2e6; padding: 4px 8px; "
            "border-radius: 4px; font-size: 12px; cursor: pointer; transition: all 0.15s;' "
            "onmouseover=\"this.style.background='#e9ecef';\" "
            "onmouseout=\"this.style.background='transparent';\" "
            "title='Copy markdown reference'>📋</button>",
            obj.key,
        )

    @admin.display(description="Type", ordering="asset_type")
    def asset_type_badge(self, obj):
        """Display asset type with colored badge."""
        icons = {
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "document": "📄",
            "archive": "📦",
            "other": "📎",
        }
        colors = {
            "image": "#e3f2fd",
            "video": "#fce4ec",
            "audio": "#f3e5f5",
            "document": "#fff3e0",
            "archive": "#e8f5e9",
            "other": "#f5f5f5",
        }
        text_colors = {
            "image": "#1976d2",
            "video": "#c2185b",
            "audio": "#7b1fa2",
            "document": "#ef6c00",
            "archive": "#388e3c",
            "other": "#616161",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500;">{} {}</span>',
            colors.get(obj.asset_type, "#f5f5f5"),
            text_colors.get(obj.asset_type, "#616161"),
            icons.get(obj.asset_type, ""),
            obj.get_asset_type_display(),
        )

    @admin.display(description="Folder")
    def folder_badge(self, obj):
        """Display asset folder."""
        if not obj.asset_folder:
            return format_html('<span style="color: #999;">—</span>')

        # Show folder icon and name
        depth = obj.asset_folder.path.count("/")
        icon = "📁" if depth > 0 else "📂"

        return format_html(
            '<span style="background: #fff3e0; color: #e65100; padding: 4px 8px; border-radius: 4px; font-size: 11px;">'
            "{} {}"
            "</span>",
            icon,
            obj.asset_folder.name,
        )

    @admin.display(description="Collections")
    def collection_badge(self, obj):
        """Display collections as badges."""
        collections = obj.collections.all()[:3]  # Show up to 3 collections
        if not collections:
            return format_html('<span style="color: #999;">—</span>')

        badges = []
        for collection in collections:
            badges.append(
                f'<span style="background: #f3e5f5; color: #7b1fa2; padding: 4px 8px; border-radius: 4px; font-size: 11px; margin-right: 4px;">{collection.name}</span>'
            )

        # Show count if more than 3
        if obj.collections.count() > 3:
            badges.append(
                f'<span style="color: #999; font-size: 11px;">+{obj.collections.count() - 3} more</span>'
            )

        return format_html("".join(badges))

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        """Display status with appropriate color."""
        colors = {
            "draft": "#fff3cd",  # warning yellow
            "ready": "#d4edda",  # success green
            "archived": "#e2e3e5",  # gray
        }
        text_colors = {
            "draft": "#856404",
            "ready": "#155724",
            "archived": "#383d41",
        }
        bg_color = colors.get(obj.status, "#e2e3e5")
        text_color = text_colors.get(obj.status, "#383d41")
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500;">{}</span>',
            bg_color,
            text_color,
            obj.get_status_display(),
        )

    @admin.display(description="Usage", ordering="usage_count")
    def usage_indicator(self, obj):
        """Visual indicator of asset usage."""
        if obj.usage_count == 0:
            return format_html('<span style="color: #999;">Unused</span>')
        elif obj.usage_count <= 3:
            color = "#0288d1"  # blue
        elif obj.usage_count <= 10:
            color = "#388e3c"  # green
        else:
            color = "#7b1fa2"  # purple

        return format_html(
            '<strong style="color: {};">{}</strong> <span style="color: #666;">post{}</span>',
            color,
            obj.usage_count,
            "s" if obj.usage_count != 1 else "",
        )

    @admin.display(description="Asset Preview")
    def preview_large(self, obj):
        """Show full preview in detail view."""
        if obj.asset_type == "image" and obj.file:
            return format_html(
                '<img src="{}" style="max-width: 600px; max-height: 400px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);" />',
                obj.file.url,
            )
        elif obj.asset_type == "video" and obj.file:
            return format_html(
                '<video controls width="600" style="border-radius: 8px;"><source src="{}" type="{}"></video>',
                obj.file.url,
                obj.mime_type or "video/mp4",
            )
        elif obj.asset_type == "audio" and obj.file:
            return format_html(
                '<audio controls style="width: 600px;"><source src="{}" type="{}"></audio>',
                obj.file.url,
                obj.mime_type or "audio/mpeg",
            )
        return format_html(
            '<a href="{}" target="_blank" style="padding: 8px 16px; background: #007bff; color: white; border-radius: 4px; text-decoration: none;">Download File</a>',
            obj.file.url,
        )

    @admin.display(description="Metadata Status")
    def metadata_status_detailed(self, obj):
        """Display metadata completeness status in detail view."""
        checks = {
            "File size": obj.file_size is not None,
            "MIME type": bool(obj.mime_type),
        }

        # Add dimension checks for images and videos
        if obj.asset_type in ["image", "video"]:
            checks["Width"] = obj.width is not None
            checks["Height"] = obj.height is not None

        # Add duration check for videos and audio
        if obj.asset_type in ["video", "audio"]:
            checks["Duration"] = obj.duration is not None

        # Count missing fields
        missing = [name for name, present in checks.items() if not present]
        total = len(checks)
        present = total - len(missing)

        # Build status message
        if not missing:
            status_html = f'<strong style="color: #28a745;">✓ Complete</strong> ({present}/{total} fields)'
        else:
            status_html = f'<strong style="color: #ff9800;">⚠ Incomplete</strong> ({present}/{total} fields)<br>'
            status_html += (
                f'<span style="color: #666;">Missing: {", ".join(missing)}</span><br>'
            )
            status_html += '<em style="color: #666;">Use "Populate metadata" action to auto-fill</em>'

        return format_html(status_html)

    @admin.display(description="Auto-Generated Key Preview")
    def key_preview(self, obj):
        """Show preview of what the auto-generated key will be."""
        if obj.key:
            # Already has a key
            return format_html("<p>✓ Key is set: <code>{}</code></p>", obj.key)

        # Preview what will be generated
        if not obj.title:
            return format_html(
                "<p><em>⚠ Enter a title to see auto-generated key preview</em></p>"
            )

        from django.template.defaultfilters import slugify

        base_slug = slugify(obj.title) or "asset"

        # Simulate what _generate_unique_key would create
        type_prefixes = {
            "image": "img",
            "video": "vid",
            "audio": "aud",
            "document": "doc",
            "archive": "arc",
            "other": "asset",
        }
        type_prefix = type_prefixes.get(obj.asset_type, "asset")

        if obj.collection:
            collection_slug = slugify(obj.collection)
            preview_key = f"{collection_slug}/{type_prefix}-{base_slug}"
        else:
            preview_key = f"{type_prefix}-{base_slug}"

        parts = []
        parts.append(f"{type_prefix} prefix")
        if obj.collection:
            parts.append(f"collection ({obj.collection})")
        parts.append("title slug")

        return format_html(
            "<p>🔮 Auto-generated key will be: <code>{}</code><br>"
            "<small>Includes: {} (unique suffix added if needed)</small></p>",
            preview_key,
            " + ".join(parts),
        )

    @admin.display(description="Markdown Reference")
    def markdown_reference_copyable(self, obj):
        """Copyable markdown reference with copy button."""
        return format_html(
            '<div style="display: flex; align-items: center; gap: 8px;">'
            "<code>@asset:{}</code>"
            "<button type='button' "
            "onclick=\"navigator.clipboard.writeText('@asset:{}').then(() => {{ "
            "const orig = this.textContent; "
            "this.textContent = '✓ Copied'; "
            "setTimeout(() => {{ this.textContent = orig; }}, 2000); "
            '}}); event.preventDefault();">Copy</button>'
            "</div>",
            obj.key,
            obj.key,
        )

    @admin.display(description="Usage Examples")
    def markdown_usage_examples(self, obj):
        """Show markdown usage examples."""
        examples = {
            "image": f"@asset:{obj.key}",
            "video": f"@asset:{obj.key}",
            "audio": f"@asset:{obj.key}",
            "document": f"[Download {obj.title}](@asset:{obj.key})",
            "archive": f"[Download {obj.title}](@asset:{obj.key})",
            "other": f"@asset:{obj.key}",
        }
        example = examples.get(obj.asset_type, f"@asset:{obj.key}")

        return format_html(
            "<div>"
            "<strong>Example usage:</strong><br>"
            "<code>{}</code> "
            "<button type='button' "
            "onclick=\"navigator.clipboard.writeText('{}').then(() => {{ "
            "const orig = this.textContent; "
            "this.textContent = '✓ Copied'; "
            "setTimeout(() => {{ this.textContent = orig; }}, 2000); "
            '}}); event.preventDefault();">Copy</button>'
            "</div>",
            example,
            example,
        )

    @admin.display(description="Usage")
    def usage_list(self, obj):
        """Show list of posts using this asset."""
        usages = obj.post_usages.select_related("post")[:10]
        if not usages:
            return format_html('<em style="color: #999;">Not used in any posts</em>')

        html = '<ul style="margin: 0; padding-left: 20px;">'
        for usage in usages:
            post_url = f"/admin/engine/post/{usage.post.pk}/change/"
            html += f"""
            <li style="margin: 4px 0;">
                <a href="{post_url}" target="_blank">{usage.post.title}</a>
                {f'<code style="background: #f0f0f0; padding: 2px 4px; margin-left: 4px; border-radius: 2px;">@{usage.alias}</code>' if usage.alias else ""}
            </li>
            """
        html += "</ul>"

        total = obj.post_usages.count()
        if total > 10:
            html += f'<p style="margin: 8px 0 0 0; color: #666;"><em>...and {total - 10} more</em></p>'

        return format_html(html)

    @admin.action(description="Generate renditions for selected images")
    def generate_renditions(self, request, queryset):
        """Admin action to generate renditions for selected images."""
        from engine.utils import generate_asset_renditions

        count = 0
        for asset in queryset.filter(asset_type="image"):
            generate_asset_renditions(asset)
            count += 1

        self.message_user(request, f"Generated renditions for {count} image(s).")

    @admin.action(description="Update usage count")
    def update_usage_count(self, request, queryset):
        """Update usage count for selected assets."""
        for asset in queryset:
            asset.usage_count = asset.post_usages.count()
            asset.save(update_fields=["usage_count"])

        self.message_user(
            request, f"Updated usage count for {queryset.count()} asset(s)."
        )

    @admin.action(description="Regenerate keys with organized format")
    def regenerate_keys(self, request, queryset):
        """Regenerate asset keys using the new organized format."""
        from django.template.defaultfilters import slugify

        regenerated = 0
        errors = []

        for asset in queryset:
            old_key = asset.key
            try:
                # Temporarily clear key to trigger regeneration
                asset.key = ""
                # Generate new organized key
                base_slug = slugify(asset.title) or "asset"
                asset.key = asset._generate_unique_key(base_slug)
                asset.save(update_fields=["key"])

                regenerated += 1
                self.message_user(
                    request,
                    f"✓ {asset.title}: '{old_key}' → '{asset.key}'",
                    level="success",
                )
            except Exception as e:
                errors.append(f"{asset.title}: {str(e)}")
                # Restore old key on error
                asset.key = old_key
                asset.save(update_fields=["key"])

        if regenerated > 0:
            self.message_user(
                request,
                f"Regenerated {regenerated} asset key(s) with organized format.",
                level="success",
            )

        if errors:
            for error in errors:
                self.message_user(request, f"Error: {error}", level="error")

    @admin.action(description="Populate metadata (dimensions, MIME type, file size)")
    def populate_metadata(self, request, queryset):
        """Admin action to populate metadata for selected assets."""
        from engine.utils import populate_asset_metadata

        count = 0
        errors = 0
        for asset in queryset:
            try:
                populate_asset_metadata(Asset, asset, created=False)
                count += 1
            except Exception as e:
                errors += 1
                self.message_user(
                    request, f"Error processing {asset.key}: {str(e)}", level="error"
                )

        if count > 0:
            self.message_user(
                request, f"Successfully populated metadata for {count} asset(s)."
            )
        if errors > 0:
            self.message_user(
                request,
                f"Failed to process {errors} asset(s). Check error messages above.",
                level="warning",
            )

    @admin.action(description="Extract extended metadata (EXIF, audio tags, etc.)")
    def extract_extended_metadata(self, request, queryset):
        """Admin action to extract extended metadata (EXIF, audio tags, document info, colors)."""
        from engine.metadata_extractor import extract_all_metadata

        successful = 0
        skipped = 0
        errors = []

        for asset in queryset:
            try:
                metadata = extract_all_metadata(asset)
                if metadata:
                    successful += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{asset.key}: {str(e)}")

        # Show results
        if successful > 0:
            self.message_user(
                request,
                f"✓ Successfully extracted metadata for {successful} asset(s).",
                level=messages.SUCCESS,
            )

        if skipped > 0:
            self.message_user(
                request,
                f"⚠ Skipped {skipped} asset(s) (no metadata available or unsupported type).",
                level=messages.WARNING,
            )

        if errors:
            for error in errors[:5]:  # Show first 5 errors
                self.message_user(request, f"✗ Error: {error}", level=messages.ERROR)
            if len(errors) > 5:
                self.message_user(
                    request,
                    f"...and {len(errors) - 5} more errors.",
                    level=messages.ERROR,
                )

    @admin.action(description="Extract metadata (async with Celery)")
    def extract_metadata_async_action(self, request, queryset):
        """Admin action to extract metadata asynchronously using Celery."""
        try:
            from engine.tasks import bulk_extract_metadata

            asset_ids = list(queryset.values_list("pk", flat=True))

            # Queue the task
            result = bulk_extract_metadata.delay(asset_ids)

            self.message_user(
                request,
                f"✓ Queued metadata extraction for {len(asset_ids)} asset(s). "
                f"Task ID: {result.id}",
                level=messages.SUCCESS,
            )

        except ImportError:
            self.message_user(
                request,
                "⚠ Celery is not installed. Use 'Extract extended metadata' action instead for synchronous processing.",
                level=messages.WARNING,
            )
        except Exception as e:
            self.message_user(
                request,
                f"✗ Error queuing task: {str(e)}",
                level=messages.ERROR,
            )

    @admin.action(description="Mark as Ready")
    def mark_as_ready(self, request, queryset):
        """Mark selected assets as ready."""
        count = queryset.update(status="ready")
        self.message_user(request, f"Marked {count} asset(s) as ready.")

    @admin.action(description="Mark as Archived")
    def mark_as_archived(self, request, queryset):
        """Mark selected assets as archived."""
        count = queryset.update(status="archived")
        self.message_user(request, f"Marked {count} asset(s) as archived.")

    @admin.action(description="Export metadata as CSV")
    def export_metadata_csv(self, request, queryset):
        """Export asset metadata as CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="assets_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Key",
                "Title",
                "Type",
                "Status",
                "Collection",
                "Folder",
                "File Size",
                "Width",
                "Height",
                "Duration",
                "Bitrate",
                "Frame Rate",
                "Alt Text",
                "Caption",
                "Credit",
                "License",
                "Usage Count",
                "View Count",
                "Download Count",
                "Is Public",
                "Created",
                "File URL",
            ]
        )

        for asset in queryset:
            writer.writerow(
                [
                    asset.key,
                    asset.title,
                    asset.get_asset_type_display(),
                    asset.get_status_display(),
                    asset.collection or "",
                    asset.folder or "",
                    asset.human_file_size,
                    asset.width or "",
                    asset.height or "",
                    str(asset.duration) if asset.duration else "",
                    asset.bitrate or "",
                    asset.frame_rate or "",
                    asset.alt_text,
                    asset.caption,
                    asset.credit,
                    asset.license,
                    asset.usage_count,
                    asset.view_count,
                    asset.download_count,
                    "Yes" if asset.is_public else "No",
                    asset.created_at.strftime("%Y-%m-%d %H:%M"),
                    asset.file.url if asset.file else "",
                ]
            )

        return response

    @admin.action(description="Delete orphaned renditions")
    def cleanup_orphaned_renditions(self, request, queryset):
        """Delete renditions of soft-deleted assets."""
        from engine.models import AssetRendition

        # Find renditions of soft-deleted assets in the queryset
        asset_ids = queryset.filter(is_deleted=True).values_list('id', flat=True)
        orphaned = AssetRendition.objects.filter(asset_id__in=asset_ids)

        count = orphaned.count()

        if count == 0:
            self.message_user(
                request,
                "No orphaned renditions found for selected assets.",
                level=messages.INFO
            )
            return

        # Calculate total size
        total_size = sum(r.file_size or 0 for r in orphaned)

        # Delete renditions
        deleted_count, _ = orphaned.delete()

        self.message_user(
            request,
            f"✓ Deleted {deleted_count} orphaned rendition(s) "
            f"({self._format_size(total_size)} freed)",
            level=messages.SUCCESS
        )

    @admin.action(description="Delete unused assets (not in posts)")
    def cleanup_unused_assets(self, request, queryset):
        """Delete selected assets that are not used in any posts."""
        from django.db.models import Count

        # Find unused assets in queryset
        unused = queryset.annotate(
            post_count=Count('postasset')
        ).filter(post_count=0)

        count = unused.count()

        if count == 0:
            self.message_user(
                request,
                "All selected assets are being used in posts.",
                level=messages.INFO
            )
            return

        # Calculate total size and renditions
        total_size = sum(a.file_size or 0 for a in unused)
        rendition_count = sum(a.renditions.count() for a in unused)

        # Delete assets (will cascade to renditions)
        deleted_count, details = unused.delete()

        self.message_user(
            request,
            f"✓ Deleted {deleted_count} unused asset(s) and "
            f"{details.get('engine.AssetRendition', 0)} rendition(s) "
            f"({self._format_size(total_size)} freed)",
            level=messages.SUCCESS
        )

    def _format_size(self, size_bytes):
        """Format bytes as human-readable size."""
        if size_bytes == 0:
            return '0 B'

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f'{size_bytes:.2f} {unit}'
            size_bytes /= 1024.0

        return f'{size_bytes:.2f} TB'


# --------------------------
# AssetMetadata Admin
# --------------------------
@admin.register(AssetMetadata)
class AssetMetadataAdmin(admin.ModelAdmin):
    """Admin for extended asset metadata."""

    list_display = (
        "asset_key_with_preview",
        "metadata_summary",
        "has_camera_info_display",
        "has_gps_display",
        "has_audio_info_display",
        "has_color_info_display",
        "captured_at",
        "updated_at",
    )

    list_filter = (
        "camera_make",
        "camera_model",
        "captured_at",
        "year",
        "artist",
        "album",
        "genre",
        "has_alpha",
    )

    search_fields = (
        "asset__key",
        "asset__title",
        "camera_make",
        "camera_model",
        "lens",
        "location_name",
        "artist",
        "album",
        "author",
        "subject",
    )

    list_select_related = ("asset",)
    readonly_fields = (
        "asset",
        "created_at",
        "updated_at",
        "gps_map_display",
        "color_preview_display",
    )

    fieldsets = (
        (
            "Asset",
            {
                "fields": ("asset",),
            },
        ),
        (
            "Camera & Photo Metadata",
            {
                "fields": (
                    ("camera_make", "camera_model"),
                    "lens",
                    ("focal_length", "aperture"),
                    ("shutter_speed", "iso"),
                    "captured_at",
                ),
                "classes": [],
            },
        ),
        (
            "Location (GPS)",
            {
                "fields": (
                    ("latitude", "longitude"),
                    "location_name",
                    "gps_map_display",
                ),
                "classes": [],
            },
        ),
        (
            "Audio Metadata",
            {
                "fields": (
                    ("artist", "album"),
                    ("genre", "year"),
                    "track_number",
                ),
                "classes": [],
            },
        ),
        (
            "Document Metadata",
            {
                "fields": (
                    "author",
                    "subject",
                    "keywords",
                    "page_count",
                ),
                "classes": [],
            },
        ),
        (
            "Color Information",
            {
                "fields": (
                    "color_preview_display",
                    ("average_color", "color_space"),
                    "color_profile",
                    "dominant_colors",
                    "color_palette",
                ),
                "classes": [],
            },
        ),
        (
            "Image Quality",
            {
                "fields": (("dpi", "has_alpha"),),
                "classes": [],
            },
        ),
        (
            "Extended Metadata",
            {
                "fields": (
                    "exif_data",
                    "custom_fields",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    @admin.display(description="Asset", ordering="asset__key")
    def asset_key_with_preview(self, obj):
        """Display asset key with thumbnail preview."""
        if obj.asset.asset_type == "image" and obj.asset.file:
            return format_html(
                '<div style="display: flex; align-items: center; gap: 8px;">'
                '<img src="{}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px; border: 1px solid #dee2e6;" />'
                '<a href="/admin/engine/asset/{}/change/"><code>{}</code></a>'
                "</div>",
                obj.asset.file.url,
                obj.asset.pk,
                obj.asset.key,
            )
        return format_html(
            '<a href="/admin/engine/asset/{}/change/"><code>{}</code></a>',
            obj.asset.pk,
            obj.asset.key,
        )

    @admin.display(description="Metadata Summary")
    def metadata_summary(self, obj):
        """Display compact summary of available metadata."""
        from django.utils.safestring import mark_safe

        info_parts = []

        if obj.camera_make or obj.camera_model:
            camera = f"{obj.camera_make or ''} {obj.camera_model or ''}".strip()
            info_parts.append(f"📷 {camera[:20]}")

        if obj.artist or obj.album:
            audio = f"{obj.artist or ''} - {obj.album or ''}".strip(" -")
            info_parts.append(f"🎵 {audio[:20]}")

        if obj.author:
            info_parts.append(f"📄 {obj.author[:20]}")

        if obj.has_gps:
            info_parts.append("📍 GPS")

        if obj.average_color:
            info_parts.append(
                f'<span style="display: inline-block; width: 16px; height: 16px; background: {obj.average_color}; '
                f'border: 1px solid #dee2e6; border-radius: 2px; vertical-align: middle; title="{obj.average_color}"></span>'
            )

        if not info_parts:
            return format_html('<em style="color: #999;">No metadata</em>')

        # Join with separator and mark as safe since we control the HTML
        return mark_safe(
            f'<div style="font-size: 11px;">{" • ".join(info_parts)}</div>'
        )

    @admin.display(description="Camera", boolean=True)
    def has_camera_info_display(self, obj):
        """Display if camera metadata exists."""
        return obj.has_camera_info

    @admin.display(description="GPS", boolean=True)
    def has_gps_display(self, obj):
        """Display if GPS coordinates exist."""
        return obj.has_gps

    @admin.display(description="Audio", boolean=True)
    def has_audio_info_display(self, obj):
        """Display if audio metadata exists."""
        return obj.has_audio_info

    @admin.display(description="Color", boolean=True)
    def has_color_info_display(self, obj):
        """Display if color information exists."""
        return bool(obj.average_color or obj.dominant_colors)

    @admin.display(description="GPS Location")
    def gps_map_display(self, obj):
        """Display GPS coordinates with map link."""
        if not obj.has_gps:
            return format_html('<em style="color: #999;">No GPS data available</em>')

        # Google Maps link
        maps_url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"

        return format_html(
            '<div style="padding: 8px; background: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">'
            '<div style="font-family: monospace; margin-bottom: 4px;">📍 {:.6f}, {:.6f}</div>'
            '<a href="{}" target="_blank" style="color: #007bff; text-decoration: none;">🗺️ View on Google Maps</a>'
            "</div>",
            obj.latitude,
            obj.longitude,
            maps_url,
        )

    @admin.display(description="Color Preview")
    def color_preview_display(self, obj):
        """Display visual color preview."""
        if not obj.average_color and not obj.dominant_colors:
            return format_html('<em style="color: #999;">No color data available</em>')

        html_parts = []

        # Average color swatch
        if obj.average_color:
            html_parts.append(
                f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">'
                f'<div style="width: 40px; height: 40px; background: {obj.average_color}; border-radius: 4px; '
                f'border: 1px solid #dee2e6; box-shadow: 0 1px 3px rgba(0,0,0,0.1);"></div>'
                f"<div><strong>Average:</strong> <code>{obj.average_color}</code></div>"
                f"</div>"
            )

        # Dominant colors palette
        if obj.dominant_colors and isinstance(obj.dominant_colors, list):
            swatches = []
            for color in obj.dominant_colors[:8]:  # Show up to 8 colors
                if isinstance(color, str) and color.startswith("#"):
                    swatches.append(
                        f'<div style="width: 30px; height: 30px; background: {color}; border-radius: 3px; '
                        f'border: 1px solid #dee2e6;" title="{color}"></div>'
                    )

            if swatches:
                html_parts.append(
                    f'<div style="margin-top: 8px;">'
                    f'<div style="font-weight: 500; margin-bottom: 4px;">Dominant Colors:</div>'
                    f'<div style="display: flex; gap: 4px; flex-wrap: wrap;">{"".join(swatches)}</div>'
                    f"</div>"
                )

        return format_html(
            "".join(html_parts)
            if html_parts
            else '<em style="color: #999;">No color preview available</em>'
        )


# --------------------------
# AssetRendition Admin
# --------------------------
@admin.register(AssetRendition)
class AssetRenditionAdmin(admin.ModelAdmin):
    """Admin for asset renditions."""

    list_display = (
        "rendition_display",
        "asset_key",
        "width",
        "height",
        "format",
        "quality",
        "preset_badge",
        "file_size_display",
        "status_badge",
    )

    list_filter = (
        "format",
        "quality",
        "status",
        "preset",
        "is_webp",
        "created_at",
    )

    search_fields = ("asset__key", "asset__title", "preset")

    readonly_fields = ("asset", "file_size", "created_at", "updated_at")

    list_select_related = ["asset"]

    fieldsets = (
        (
            "Rendition Details",
            {
                "fields": (
                    "asset",
                    ("width", "height"),
                    ("format", "quality"),
                    "preset",
                ),
                "classes": [],
            },
        ),
        (
            "File",
            {
                "fields": (
                    "file",
                    "file_size",
                    "cdn_url",
                ),
                "classes": [],
            },
        ),
        (
            "Media Settings",
            {
                "fields": (
                    ("bitrate", "codec"),
                    "is_webp",
                ),
                "classes": ["collapse", "unfold-column-2"],
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "error_message",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    @admin.display(description="Preview")
    def rendition_display(self, obj):
        """Show rendition preview."""
        if obj.file:
            return format_html(
                '<img src="{}" style="max-width: 80px; max-height: 60px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);" />',
                obj.file.url,
            )
        return "-"

    @admin.display(description="Asset")
    def asset_key(self, obj):
        """Display asset key with link."""
        return format_html(
            '<a href="/admin/engine/asset/{}/change/"><code>{}</code></a>',
            obj.asset.pk,
            obj.asset.key,
        )

    @admin.display(description="Preset")
    def preset_badge(self, obj):
        """Display preset as badge."""
        if not obj.preset:
            return format_html('<span style="color: #999;">—</span>')
        return format_html(
            '<span style="background: #e3f2fd; color: #1976d2; padding: 4px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            obj.preset,
        )

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        return obj.human_file_size

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            "pending": "#fff3cd",
            "processing": "#cfe2ff",
            "completed": "#d4edda",
            "failed": "#f8d7da",
        }
        text_colors = {
            "pending": "#856404",
            "processing": "#084298",
            "completed": "#155724",
            "failed": "#721c24",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            colors.get(obj.status, "#e2e3e5"),
            text_colors.get(obj.status, "#383d41"),
            obj.get_status_display(),
        )


# --------------------------
# Asset Organization Admins
# --------------------------
@admin.register(AssetFolder)
class AssetFolderAdmin(admin.ModelAdmin):
    """Admin for asset folder hierarchy."""

    list_display = (
        "folder_name_with_icon",
        "user",
        "asset_count_display",
        "created_at",
    )
    list_filter = ("user", "created_at")
    search_fields = ("name", "path")
    autocomplete_fields = ["user", "parent"]
    readonly_fields = ("path", "created_at", "updated_at")
    ordering = ["path"]

    def get_search_results(self, request, queryset, search_term):
        """Enable autocomplete search."""
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        return queryset, may_have_duplicates

    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("name", "parent"),
                    ("user",),
                    ("path",),
                ),
                "classes": [],
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    @admin.display(description="Folder", ordering="path")
    def folder_name_with_icon(self, obj):
        """Display folder with icon and hierarchy."""
        depth = obj.path.count("/")
        indent = "&nbsp;" * (depth * 4)
        icon = "📁" if obj.children.exists() else "📂"

        return format_html(
            '{}<span style="font-size: 16px;">{}</span> <strong>{}</strong>',
            indent,
            icon,
            obj.name,
        )

    @admin.display(description="Assets")
    def asset_count_display(self, obj):
        """Display number of assets in folder."""
        count = obj.folder_assets.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<span style="background: #e7f3ff; color: #004085; padding: 2px 8px; border-radius: 3px; font-weight: 500;">{}</span>',
            count,
        )


@admin.register(AssetTag)
class AssetTagAdmin(admin.ModelAdmin):
    """Admin for asset tags."""

    list_display = ("tag_display", "slug", "asset_count_display", "color_preview")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("name", "slug"),
                    ("color",),
                ),
            },
        ),
    )

    @admin.display(description="Tag", ordering="name")
    def tag_display(self, obj):
        """Display tag with color badge."""
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; border-radius: 4px; font-weight: 500;">{}</span>',
            obj.color,
            obj.name,
        )

    @admin.display(description="Assets")
    def asset_count_display(self, obj):
        """Display number of assets with this tag."""
        count = obj.tagged_assets.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<span style="background: {}20; color: {}; padding: 2px 8px; border-radius: 3px; font-weight: 500;">{}</span>',
            obj.color,
            obj.color,
            count,
        )

    @admin.display(description="Preview")
    def color_preview(self, obj):
        """Show color swatch."""
        return format_html(
            '<div style="width: 40px; height: 20px; background: {}; border: 1px solid #dee2e6; border-radius: 3px;"></div>',
            obj.color,
        )


@admin.register(AssetCollection)
class AssetCollectionAdmin(admin.ModelAdmin):
    """Admin for asset collections."""

    list_display = (
        "collection_name_with_cover",
        "user",
        "asset_count_display",
        "is_public",
        "created_at",
    )
    list_filter = ("is_public", "user", "created_at")
    search_fields = ("name", "description")
    autocomplete_fields = ["user", "cover_asset"]
    filter_horizontal = ["assets"]
    readonly_fields = ("created_at", "updated_at", "asset_count_display")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("name",),
                    ("description",),
                    ("user", "is_public"),
                    ("cover_asset",),
                ),
                "classes": [],
            },
        ),
        (
            "Assets",
            {
                "fields": (("asset_count_display",), ("assets",)),
                "description": "Add assets to this collection",
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    @admin.display(description="Collection", ordering="name")
    def collection_name_with_cover(self, obj):
        """Display collection with cover image."""
        if (
            obj.cover_asset
            and obj.cover_asset.asset_type == "image"
            and obj.cover_asset.file
        ):
            return format_html(
                '<div style="display: flex; align-items: center; gap: 10px;">'
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 6px; border: 1px solid #dee2e6;" />'
                "<div>"
                '<div style="font-weight: 600;">{}</div>'
                '<div style="font-size: 11px; color: #6c757d;">{}</div>'
                "</div>"
                "</div>",
                obj.cover_asset.file.url,
                obj.name,
                "Public" if obj.is_public else "Private",
            )

        icon = "🌍" if obj.is_public else "🔒"
        return format_html(
            '<div style="display: flex; align-items: center; gap: 10px;">'
            '<div style="width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; '
            'background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; font-size: 24px;">{}</div>'
            "<div>"
            '<div style="font-weight: 600;">{}</div>'
            '<div style="font-size: 11px; color: #6c757d;">{}</div>'
            "</div>"
            "</div>",
            icon,
            obj.name,
            "Public" if obj.is_public else "Private",
        )

    @admin.display(description="Assets")
    def asset_count_display(self, obj):
        """Display number of assets in collection."""
        count = obj.asset_count()
        if count == 0:
            return format_html(
                '<span style="color: #999; font-style: italic;">No assets yet</span>'
            )
        return format_html(
            '<span style="background: #e7f3ff; color: #004085; padding: 4px 12px; border-radius: 4px; font-weight: 600;">'
            "{} asset{}"
            "</span>",
            count,
            "s" if count != 1 else "",
        )
