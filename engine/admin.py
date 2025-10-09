# admin.py
import csv

from django.contrib import admin, messages
from django.contrib.admin.widgets import AdminTextareaWidget
from django.db import models
from django.http import HttpResponse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.decorators import display, action

from .models import (
    Post,
    Tag,
    Category,
    Series,
    Asset,
    AssetMetadata,
    AssetRendition,
    PostAsset,
    AssetFolder,
    AssetTag,
    AssetCollection,
    InternalLink,
)


# --------------------------
# Shared admin mixin for soft-delete
# --------------------------
class SoftDeleteAdminMixin(ModelAdmin):
    """Show ALL objects in admin (including soft-deleted), add actions to delete/restore."""

    def get_queryset(self, request):
        # Use the 'all_objects' manager so admins can see and restore soft-deleted rows.
        qs = super().get_queryset(request)
        if hasattr(self.model, "all_objects"):
            return self.model.all_objects.get_queryset()
        return qs

    @action(description="Soft delete selected")
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

    @action(description="Restore selected (clear soft delete)")
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


# --------------------------
# Simple taxonomy admins
# --------------------------
@admin.register(Tag)
class TagAdmin(ModelAdmin):
    list_display = (
        "name",
        "slug",
        "asset_count",
        "post_count",
        "created_at",
        "updated_at",
    )
    search_fields = ("name",)
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 50

    @display(description="Assets", ordering="assets__count")
    def asset_count(self, obj):
        count = obj.assets.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<a href="/admin/engine/asset/?tags__id__exact={}" style="font-weight: 500;">{}</a>',
            obj.pk,
            count,
        )

    @display(description="Posts", ordering="posts__count")
    def post_count(self, obj):
        count = obj.posts.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<a href="/admin/engine/post/?tags__id__exact={}" style="font-weight: 500;">{}</a>',
            obj.pk,
            count,
        )


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("name", "slug", "parent", "post_count", "created_at", "updated_at")
    list_filter = ("parent",)
    search_fields = ("name", "description")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("parent",)
    list_select_related = ("parent",)
    list_per_page = 50

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (("name", "slug"), "description", "parent"),
                "classes": ["unfold-column-2"],
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

    readonly_fields = ("created_at", "updated_at")

    @display(description="Posts", ordering="posts__count")
    def post_count(self, obj):
        count = obj.posts.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<a href="/admin/engine/post/?categories__id__exact={}" style="font-weight: 500;">{}</a>',
            obj.pk,
            count,
        )


@admin.register(Series)
class SeriesAdmin(ModelAdmin):
    list_display = ("title", "slug", "post_count", "created_at", "updated_at")
    search_fields = ("title", "description")
    ordering = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    list_per_page = 50

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (("title", "slug"), "description"),
                "classes": ["unfold-column-2"],
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

    readonly_fields = ("created_at", "updated_at")

    @display(description="Posts", ordering="posts__count")
    def post_count(self, obj):
        count = obj.posts.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<a href="/admin/engine/post/?series__id__exact={}" style="font-weight: 500;">{}</a>',
            obj.pk,
            count,
        )

    class Meta:
        verbose_name_plural = "series"


# --------------------------
# Asset system admins
# --------------------------


class AssetMetadataInline(StackedInline):
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

    @display(description="GPS Location")
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

    @display(description="Color Preview")
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


class AssetRenditionInline(TabularInline):
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

    @display(description="Preview")
    def rendition_preview(self, obj):
        """Show thumbnail of rendition."""
        if obj.file:
            return format_html(
                '<img src="{}" style="max-width: 80px; max-height: 60px; border-radius: 4px;" />',
                obj.file.url,
            )
        return "-"

    @display(description="File Size")
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        return obj.human_file_size


@admin.register(Asset)
class AssetAdmin(SoftDeleteAdminMixin):
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
                "classes": ["unfold-column-2"],
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
                "classes": ["unfold-column-2"],
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
                "classes": ["unfold-column-2", "collapse"],
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
        "populate_metadata",
        "extract_extended_metadata",
        "extract_metadata_async_action",
        "generate_renditions",
        "update_usage_count",
        "regenerate_keys",
        "mark_as_ready",
        "mark_as_archived",
        "bulk_add_to_collection",
        "bulk_change_status",
        "export_metadata_csv",
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

    @display(description="Asset", ordering="title")
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

    @display(description="Key", ordering="key")
    def key_display(self, obj):
        """Display key in compact format."""
        return format_html(
            '<code style="font-size: 11px; color: #495057; background: #f8f9fa; '
            'padding: 3px 6px; border-radius: 3px; font-family: monospace;">{}</code>',
            obj.key,
        )

    @display(description="File Info")
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

    @display(description="📋")
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

    @display(description="Type", ordering="asset_type")
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

    @display(description="Folder")
    def folder_badge(self, obj):
        """Display asset folder."""
        if not obj.asset_folder:
            return format_html('<span style="color: #999;">—</span>')

        # Show folder icon and name
        depth = obj.asset_folder.path.count("/")
        icon = "📁" if depth > 0 else "📂"

        return format_html(
            '<span style="background: #fff3e0; color: #e65100; padding: 4px 8px; border-radius: 4px; font-size: 11px;">'
            '{} {}'
            '</span>',
            icon,
            obj.asset_folder.name
        )

    @display(description="Collections")
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
            badges.append(f'<span style="color: #999; font-size: 11px;">+{obj.collections.count() - 3} more</span>')

        return format_html(''.join(badges))

    @display(description="Status", ordering="status")
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

    @display(description="Usage", ordering="usage_count")
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

    @display(description="Asset Preview")
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

    @display(description="Metadata Status")
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

    @display(description="Auto-Generated Key Preview")
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

    @display(description="Markdown Reference")
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

    @display(description="Usage Examples")
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

    @display(description="Usage")
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
                {f'<code style="background: #f0f0f0; padding: 2px 4px; margin-left: 4px; border-radius: 2px;">@{usage.alias}</code>' if usage.alias else ''}
            </li>
            """
        html += "</ul>"

        total = obj.post_usages.count()
        if total > 10:
            html += f'<p style="margin: 8px 0 0 0; color: #666;"><em>...and {total - 10} more</em></p>'

        return format_html(html)

    @action(description="Generate renditions for selected images")
    def generate_renditions(self, request, queryset):
        """Admin action to generate renditions for selected images."""
        from .utils import generate_asset_renditions

        count = 0
        for asset in queryset.filter(asset_type="image"):
            generate_asset_renditions(asset)
            count += 1

        self.message_user(request, f"Generated renditions for {count} image(s).")

    @action(description="Update usage count")
    def update_usage_count(self, request, queryset):
        """Update usage count for selected assets."""
        for asset in queryset:
            asset.usage_count = asset.post_usages.count()
            asset.save(update_fields=["usage_count"])

        self.message_user(
            request, f"Updated usage count for {queryset.count()} asset(s)."
        )

    @action(description="Regenerate keys with organized format")
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

    @action(description="Populate metadata (dimensions, MIME type, file size)")
    def populate_metadata(self, request, queryset):
        """Admin action to populate metadata for selected assets."""
        from .utils import populate_asset_metadata

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

    @action(description="Extract extended metadata (EXIF, audio tags, etc.)")
    def extract_extended_metadata(self, request, queryset):
        """Admin action to extract extended metadata (EXIF, audio tags, document info, colors)."""
        from .metadata_extractor import extract_all_metadata

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

    @action(description="Extract metadata (async with Celery)")
    def extract_metadata_async_action(self, request, queryset):
        """Admin action to extract metadata asynchronously using Celery."""
        try:
            from .tasks import bulk_extract_metadata

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

    @action(description="Mark as Ready")
    def mark_as_ready(self, request, queryset):
        """Mark selected assets as ready."""
        count = queryset.update(status="ready")
        self.message_user(request, f"Marked {count} asset(s) as ready.")

    @action(description="Mark as Archived")
    def mark_as_archived(self, request, queryset):
        """Mark selected assets as archived."""
        count = queryset.update(status="archived")
        self.message_user(request, f"Marked {count} asset(s) as archived.")

    @action(description="Add selected to collection")
    def bulk_add_to_collection(self, request, queryset):
        """Bulk add assets to a collection."""
        self.message_user(
            request,
            f"To add {queryset.count()} asset(s) to a collection, edit the collection field directly.",
            level="info",
        )

    @action(description="Bulk change status")
    def bulk_change_status(self, request, queryset):
        """Bulk change asset status."""
        self.message_user(
            request,
            f"To change status for {queryset.count()} asset(s), edit the status field directly.",
            level="info",
        )

    @action(description="Export metadata as CSV")
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


@admin.register(AssetMetadata)
class AssetMetadataAdmin(ModelAdmin):
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
                "classes": ["unfold-column-2"],
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
                "classes": ["unfold-column-2"],
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
                "classes": ["unfold-column-2"],
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
                "classes": ["unfold-column-2"],
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
                "classes": ["unfold-column-2"],
            },
        ),
        (
            "Image Quality",
            {
                "fields": (("dpi", "has_alpha"),),
                "classes": ["unfold-column-2"],
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

    @display(description="Asset", ordering="asset__key")
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

    @display(description="Metadata Summary")
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

    @display(description="Camera", boolean=True)
    def has_camera_info_display(self, obj):
        """Display if camera metadata exists."""
        return obj.has_camera_info

    @display(description="GPS", boolean=True)
    def has_gps_display(self, obj):
        """Display if GPS coordinates exist."""
        return obj.has_gps

    @display(description="Audio", boolean=True)
    def has_audio_info_display(self, obj):
        """Display if audio metadata exists."""
        return obj.has_audio_info

    @display(description="Color", boolean=True)
    def has_color_info_display(self, obj):
        """Display if color information exists."""
        return bool(obj.average_color or obj.dominant_colors)

    @display(description="GPS Location")
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

    @display(description="Color Preview")
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


@admin.register(AssetRendition)
class AssetRenditionAdmin(ModelAdmin):
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
                "classes": ["unfold-column-2"],
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
                "classes": ["unfold-column-2"],
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

    @display(description="Preview")
    def rendition_display(self, obj):
        """Show rendition preview."""
        if obj.file:
            return format_html(
                '<img src="{}" style="max-width: 80px; max-height: 60px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);" />',
                obj.file.url,
            )
        return "-"

    @display(description="Asset")
    def asset_key(self, obj):
        """Display asset key with link."""
        return format_html(
            '<a href="/admin/engine/asset/{}/change/"><code>{}</code></a>',
            obj.asset.pk,
            obj.asset.key,
        )

    @display(description="Preset")
    def preset_badge(self, obj):
        """Display preset as badge."""
        if not obj.preset:
            return format_html('<span style="color: #999;">—</span>')
        return format_html(
            '<span style="background: #e3f2fd; color: #1976d2; padding: 4px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            obj.preset,
        )

    @display(description="File Size")
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        return obj.human_file_size

    @display(description="Status", ordering="status")
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


class PostAssetInline(StackedInline):
    model = PostAsset
    extra = 1
    min_num = 0
    max_num = 50

    autocomplete_fields = ["asset"]
    ordering = ["order"]

    # Verbose names for better UX
    verbose_name = "Asset"
    verbose_name_plural = "Post Assets"

    fieldsets = [
        (
            None,
            {
                "fields": (
                    ("asset_preview", "asset"),
                    ("alias", "order", "markdown_ref_display"),
                ),
                "classes": ["unfold-column-2"],
            },
        ),
        (
            "Custom Overrides (Optional)",
            {
                "fields": (
                    ("custom_alt_text",),
                    ("custom_caption",),
                ),
                "classes": ["collapse"],
                "description": "Override default asset metadata for this post only",
            },
        ),
    ]

    readonly_fields = ["asset_preview", "markdown_ref_display"]

    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to improve UX."""
        formset = super().get_formset(request, obj, **kwargs)

        # Make alias not required
        if "alias" in formset.form.base_fields:
            formset.form.base_fields["alias"].required = False
            formset.form.base_fields["alias"].help_text = (
                'Optional: Short name for this post (e.g., "fig1")'
            )
            formset.form.base_fields["alias"].widget.attrs.update(
                {"placeholder": "Leave blank to use global key"}
            )

        # Improve order field
        if "order" in formset.form.base_fields:
            formset.form.base_fields["order"].help_text = (
                "Display order (lower numbers first)"
            )

        # Improve custom fields help text
        if "custom_caption" in formset.form.base_fields:
            formset.form.base_fields["custom_caption"].help_text = (
                "Override default caption for this post only"
            )
            formset.form.base_fields["custom_caption"].widget.attrs.update(
                {"rows": 2, "placeholder": "Leave blank to use asset's default caption"}
            )

        if "custom_alt_text" in formset.form.base_fields:
            formset.form.base_fields["custom_alt_text"].help_text = (
                "Override default alt text for this post only"
            )
            formset.form.base_fields["custom_alt_text"].widget.attrs.update(
                {"placeholder": "Leave blank to use asset's default alt text"}
            )

        return formset

    @display(description="Preview")
    def asset_preview(self, obj):
        """Show enhanced preview in inline."""
        if not obj.asset or not obj.asset.file:
            return format_html(
                '<div style="width: 120px; height: 90px; display: flex; flex-direction: column; align-items: center; justify-content: center; '
                'background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 6px; color: #6c757d;">'
                '<span style="font-size: 32px; margin-bottom: 4px;">📎</span>'
                '<span style="font-size: 11px; opacity: 0.7;">No asset</span>'
                "</div>"
            )

        if obj.asset.asset_type == "image":
            return format_html(
                '<div style="text-align: center;">'
                '<img src="{}" style="max-width: 120px; max-height: 90px; border-radius: 6px; '
                'box-shadow: 0 2px 4px rgba(0,0,0,0.15); border: 1px solid #e9ecef; display: block; margin-bottom: 4px;" />'
                '<div style="font-size: 10px; color: #6c757d;">{} × {}</div>'
                "</div>",
                obj.asset.file.url,
                obj.asset.width or "?",
                obj.asset.height or "?",
            )

        icons_info = {
            "video": ("🎬", "Video", "#dc3545"),
            "audio": ("🎵", "Audio", "#198754"),
            "document": ("📄", "Document", "#0dcaf0"),
            "archive": ("📦", "Archive", "#6610f2"),
            "other": ("📎", "File", "#6c757d"),
        }
        icon, label, color = icons_info.get(
            obj.asset.asset_type, ("📎", "File", "#6c757d")
        )

        return format_html(
            '<div style="width: 120px; height: 90px; display: flex; flex-direction: column; align-items: center; justify-content: center; '
            'background: {}; border-radius: 6px; border: 1px solid {}; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">'
            '<span style="font-size: 40px; opacity: 0.9; margin-bottom: 4px;">{}</span>'
            '<span style="font-size: 11px; color: {}; font-weight: 500;">{}</span>'
            "</div>",
            f"{color}15",
            color,
            icon,
            color,
            label,
        )

    @display(description="Reference")
    def markdown_ref_display(self, obj):
        """Show the markdown reference with copy button."""
        # Generate reference - this displays correctly for saved objects
        if obj.pk and obj.asset:
            if obj.alias:
                ref = f"@{obj.alias}"
            else:
                ref = f"@asset:{obj.asset.key}"
        else:
            ref = "-"

        # Simple display with copy button
        return format_html(
            '<div style="display: flex; align-items: center; gap: 8px;">'
            '<code style="background: #f0f0f0; padding: 4px 8px; border-radius: 3px; font-family: monospace;">{}</code>'
            "<button type='button' "
            "style='padding: 4px 12px; cursor: pointer;' "
            'onclick="'
            "const code = this.previousElementSibling.textContent; "
            "if (code !== '-') {{ "
            "navigator.clipboard.writeText(code).then(() => {{ "
            "const orig = this.textContent; this.textContent = '✓ Copied'; "
            "setTimeout(() => {{ this.textContent = orig; }}, 2000); "
            "}}); "
            "}} else {{ "
            "alert('Please select an asset and save first'); "
            "}} "
            "event.preventDefault();"
            '">Copy</button>'
            "</div>",
            ref,
        )


# --------------------------
# Internal Links (Backlinks)
# --------------------------
@admin.register(InternalLink)
class InternalLinkAdmin(ModelAdmin):
    """Admin for internal links between posts."""

    list_display = (
        "link_display",
        "link_text_preview",
        "link_type_badge",
        "created_at",
    )
    list_filter = (
        "created_at",
        "is_deleted",
    )
    search_fields = (
        "source_post__title",
        "source_post__slug",
        "target_post__title",
        "target_post__slug",
        "link_text",
    )
    list_select_related = ("source_post", "target_post")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 100

    fieldsets = (
        (
            "Link Relationship",
            {
                "fields": (
                    ("source_post", "target_post"),
                    "link_count",
                ),
                "classes": ["unfold-column-2"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
        (
            "System",
            {
                "fields": (("is_deleted", "deleted_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    @display(description="Link", ordering="source_post__title")
    def link_display(self, obj):
        """Display the link relationship."""
        return format_html(
            '<div style="font-size: 12px;">'
            '<a href="/admin/engine/post/{}/change/" style="color: #0066cc;">{}</a>'
            '<span style="margin: 0 8px; color: #999;">→</span>'
            '<a href="/admin/engine/post/{}/change/" style="color: #0066cc;">{}</a>'
            "</div>",
            obj.source_post.pk,
            obj.source_post.title[:40],
            obj.target_post.pk,
            obj.target_post.title[:40],
        )

    @display(description="Link Text")
    def link_text_preview(self, obj):
        """Display truncated link text."""
        if not obj.link_text:
            return format_html('<span style="color: #999;">—</span>')
        text = obj.link_text[:60] + "..." if len(obj.link_text) > 60 else obj.link_text
        return format_html(
            '<span style="font-size: 11px; color: #666;">"<em>{}</em>"</span>', text
        )

    @display(description="Type")
    def link_type_badge(self, obj):
        """Display link direction."""
        return format_html(
            '<span style="background: #e7f3ff; color: #004085; padding: 4px 8px; '
            'border-radius: 4px; font-size: 10px; font-weight: 500;">Internal Link</span>'
        )


class IncomingLinksInline(TabularInline):
    """Inline to show backlinks (incoming links) in Post admin."""

    model = InternalLink
    fk_name = "target_post"
    extra = 0
    max_num = 50
    can_delete = False
    verbose_name = "Backlink"
    verbose_name_plural = "Backlinks (Posts Linking to This Post)"

    fields = ("source_post_link", "link_count", "created_at")
    readonly_fields = ("source_post_link", "link_count", "created_at")

    def has_add_permission(self, request, obj=None):
        """Backlinks are auto-generated, not manually added."""
        return False

    @display(description="Source Post")
    def source_post_link(self, obj):
        """Display source post with link to admin."""
        if not obj.pk:
            return "—"
        return format_html(
            '<a href="/admin/engine/post/{}/change/" target="_blank">{}</a>',
            obj.source_post.pk,
            obj.source_post.title,
        )


# --------------------------
# Post admin
# --------------------------
@admin.register(Post)
class PostAdmin(SoftDeleteAdminMixin):
    inlines = [PostAssetInline, IncomingLinksInline]
    save_on_top = True
    date_hierarchy = "published_at"

    list_display = (
        "post_title_with_status",
        "author",
        "status_badge",
        "completion_status_badge",
        "visibility_badge",
        "featured_pinned_indicators",
        "published_at",
        "stats_compact",
    )

    list_filter = (
        "status",
        "completion_status",
        "visibility",
        "is_featured",
        "is_pinned",
        "is_deleted",
        "published_at",
        "created_at",
        "updated_at",
        "categories",
        "tags",
        "series",
        "author",
    )

    search_fields = ("title", "subtitle", "description", "content_markdown", "slug")
    ordering = ("-is_pinned", "pin_order", "-published_at", "-created_at")

    autocomplete_fields = (
        "author",
        "co_authors",
        "series",
        "categories",
        "tags",
        "related_posts",
        "published_by",
        "last_edited_by",
    )

    filter_horizontal = ("co_authors", "categories", "tags", "related_posts")

    readonly_fields = (
        "word_count",
        "reading_time_minutes",
        "table_of_contents",
        "asset_markdown_reference_helper",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    actions = (
        "publish_selected",
        "unpublish_selected",
        "feature_selected",
        "unfeature_selected",
        "rebuild_backlinks_for_selected",
        "soft_delete_selected",
        "restore_selected",
        "export_posts_csv",
    )

    # Slug from title is handy for editors
    prepopulated_fields = {"slug": ("title",)}

    # Show facets for filters
    show_facets = admin.ShowFacets.ALWAYS

    # Optional: nicer widgets for large text fields
    formfield_overrides = {
        models.TextField: {"widget": admin.widgets.AdminTextareaWidget},
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Make text fields full-width with better editing experience
        if db_field.name == "content_markdown":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 30,
                    "cols": 120,
                    "style": "width: 100%; font-family: monospace; font-size: 16px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        elif db_field.name == "description":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 4,
                    "cols": 120,
                    "style": "width: 100%; font-size: 14px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        elif db_field.name == "abstract":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 8,
                    "cols": 120,
                    "style": "width: 100%; font-family: monospace; font-size: 14px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    ("title", "slug"),
                    ("subtitle", "language"),
                    ("author", "co_authors"),
                ),
                "classes": ["unfold-column-2"],
                "description": "Core post identity and authorship",
            },
        ),
        (
            "Publishing & Status",
            {
                "fields": (
                    ("status", "completion_status"),
                    ("visibility",),
                    ("published_at", "expire_at"),
                    ("is_featured", "is_pinned", "pin_order"),
                    ("published_by", "last_edited_by", "version"),
                ),
                "classes": ["unfold-column-2"],
                "description": "Control post status, visibility, and publication schedule",
            },
        ),
        (
            "Organization & Taxonomy",
            {
                "fields": (
                    ("series",),
                    ("categories", "tags"),
                    ("related_posts",),
                    ("show_toc", "certainty", "importance"),
                ),
                "classes": ["unfold-column-2", "collapse"],
                "description": "Categorize and relate your content",
            },
        ),
        (
            "Content",
            {
                "fields": (
                    ("description",),
                    ("abstract",),
                    ("content_markdown",),
                    ("asset_markdown_reference_helper",),
                ),
                "description": "Write your post content in Markdown. The renderer automatically processes this when displayed in templates.",
            },
        ),
        (
            "Engagement & Analytics",
            {
                "fields": (
                    ("allow_comments", "comment_count"),
                    ("view_count", "like_count", "rating"),
                    ("reading_time_minutes", "word_count"),
                ),
                "classes": ["unfold-column-3", "collapse"],
                "description": "User engagement metrics and reading statistics",
            },
        ),
        (
            "Advanced",
            {
                "fields": (
                    ("table_of_contents",),
                    ("content_html_cached",),
                    ("extras",),
                ),
                "classes": ["collapse"],
                "description": "Advanced settings and metadata",
            },
        ),
        (
            "System Information",
            {
                "fields": (
                    ("created_at", "updated_at"),
                    ("is_deleted", "deleted_at"),
                ),
                "classes": ["unfold-column-2", "collapse"],
                "description": "System-managed timestamps and soft-delete status",
            },
        ),
    )

    @display(description="Post", ordering="title")
    def post_title_with_status(self, obj):
        """Display post title with visual indicators."""
        # Status emoji
        status_icons = {
            "draft": "📝",
            "scheduled": "⏰",
            "published": "✅",
            "archived": "📦",
        }
        icon = status_icons.get(obj.status, "📄")

        # Title with bold if featured
        title_style = "font-weight: 600;" if obj.is_featured else ""

        return format_html(
            '<div style="display: flex; align-items: center; gap: 8px;">'
            '<span style="font-size: 18px;">{}</span>'
            '<span style="{}">{}</span>'
            "</div>",
            icon,
            title_style,
            obj.title,
        )

    @display(description="Status", ordering="status")
    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            "draft": "#fff3cd",
            "scheduled": "#cfe2ff",
            "published": "#d4edda",
            "archived": "#e2e3e5",
        }
        text_colors = {
            "draft": "#856404",
            "scheduled": "#084298",
            "published": "#155724",
            "archived": "#383d41",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            colors.get(obj.status, "#e2e3e5"),
            text_colors.get(obj.status, "#383d41"),
            obj.get_status_display(),
        )

    @display(description="Completion", ordering="completion_status")
    def completion_status_badge(self, obj):
        """Display completion status with color."""
        colors = {
            "finished": "#d4edda",
            "abandoned": "#f8d7da",
            "notes": "#d1ecf1",
            "draft": "#fff3cd",
            "in_progress": "#cfe2ff",
        }
        text_colors = {
            "finished": "#155724",
            "abandoned": "#721c24",
            "notes": "#0c5460",
            "draft": "#856404",
            "in_progress": "#084298",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            colors.get(obj.completion_status, "#e2e3e5"),
            text_colors.get(obj.completion_status, "#383d41"),
            obj.get_completion_status_display(),
        )

    @display(description="Visibility", ordering="visibility")
    def visibility_badge(self, obj):
        """Display visibility with color."""
        colors = {
            "public": "#d4edda",
            "unlisted": "#fff3cd",
            "private": "#f8d7da",
        }
        text_colors = {
            "public": "#155724",
            "unlisted": "#856404",
            "private": "#721c24",
        }
        icons = {
            "public": "🌐",
            "unlisted": "🔗",
            "private": "🔒",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{} {}</span>',
            colors.get(obj.visibility, "#e2e3e5"),
            text_colors.get(obj.visibility, "#383d41"),
            icons.get(obj.visibility, ""),
            obj.get_visibility_display(),
        )

    @display(description="Features")
    def featured_pinned_indicators(self, obj):
        """Show featured/pinned indicators."""
        badges = []
        if obj.is_featured:
            badges.append(
                '<span style="background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 3px; font-size: 10px;">⭐ FEATURED</span>'
            )
        if obj.is_pinned:
            badges.append(
                f'<span style="background: #e0e7ff; color: #3730a3; padding: 2px 6px; border-radius: 3px; font-size: 10px;">📌 PIN {obj.pin_order}</span>'
            )
        if not badges:
            return format_html('<span style="color: #999;">—</span>')
        return format_html(" ".join(badges))

    @display(description="Stats")
    def stats_compact(self, obj):
        """Display compact statistics."""
        return format_html(
            '<div style="font-size: 11px; color: #6c757d;">'
            "<div>👁️ {} | 💬 {} | ❤️ {}</div>"
            "<div>📖 {}min | {} words</div>"
            "</div>",
            obj.view_count,
            obj.comment_count,
            obj.like_count,
            obj.reading_time_minutes,
            obj.word_count,
        )

    @display(description="Asset Markdown References")
    def asset_markdown_reference_helper(self, obj=None):
        """Display assets attached to this post with their markdown references for quick copying."""
        from django.utils.safestring import mark_safe

        # If no post object (add page), show help message
        if not obj or not obj.pk:
            return mark_safe(
                '<div style="padding: 12px; background: #e7f3ff; border: 1px solid #0dcaf0; border-radius: 4px; color: #004085;">'
                'ℹ️ Asset references will appear here after you add assets to this post in the "Post Assets" section below.'
                "</div>"
            )

        # Get assets attached to this post via PostAsset relationship
        post_assets = obj.post_assets.select_related("asset").order_by("order")

        if not post_assets.exists():
            return mark_safe(
                '<div style="padding: 12px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
                '⚠️ No assets attached to this post yet. Add assets in the "Post Assets" section below, then save to see their markdown references here.'
                "</div>"
            )

        # Build HTML parts as a list to avoid string concatenation issues
        parts = []
        parts.append(
            '<div style="max-height: 400px; overflow-y: auto; border: 1px solid #e0e0e0; border-radius: 4px; padding: 12px; background: #f9f9f9;">'
        )
        parts.append(
            f'<div style="margin-bottom: 8px; font-weight: 600; color: #333;">📎 Assets in this Post ({post_assets.count()}) — Click to copy:</div>'
        )
        parts.append(
            '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px;">'
        )

        for post_asset in post_assets:
            asset = post_asset.asset

            # Determine the reference to use (alias or asset key)
            if post_asset.alias:
                ref = "@" + post_asset.alias
                ref_type = "Alias"
            else:
                ref = "@asset:" + asset.key
                ref_type = "Global"

            # Get asset type icon
            icons = {
                "image": "🖼️",
                "video": "🎬",
                "audio": "🎵",
                "document": "📄",
                "archive": "📦",
                "other": "📎",
            }
            icon = icons.get(asset.asset_type, "📎")

            # Truncate title
            display_title = asset.title[:40] if len(asset.title) > 40 else asset.title

            # Add order indicator
            order_badge = (
                f'<span style="background: #e9ecef; padding: 2px 6px; border-radius: 2px; font-size: 9px; font-weight: 600; margin-right: 4px;">#{post_asset.order}</span>'
                if post_asset.order
                else ""
            )

            parts.append(
                f"""
            <div class="asset-ref-card" data-ref="{ref}" style="background: white; border: 1px solid #ddd; border-radius: 3px; padding: 8px; cursor: pointer;">
                <div style="font-size: 11px; color: #666; margin-bottom: 3px;">{order_badge}{icon} {asset.asset_type.title()} <span style="color: #999;">• {ref_type}</span></div>
                <div style="font-weight: 500; font-size: 13px; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{asset.title}">{display_title}</div>
                <code style="font-size: 10px; background: #f5f5f5; padding: 2px 4px; border-radius: 2px; display: block; font-family: monospace;">{ref}</code>
            </div>
            """
            )

        parts.append("</div></div>")
        parts.append(
            '<div style="margin-top: 8px; padding: 8px; background: #e7f3ff; border-radius: 3px; font-size: 11px; color: #004085;">💡 <strong>Tip:</strong> Click any asset card above to copy its markdown reference.</div>'
        )

        # Add JavaScript for click handling
        parts.append(
            """
        <script>
        (function() {
            setTimeout(function() {
                document.querySelectorAll('.asset-ref-card').forEach(function(card) {
                    if (card.hasAttribute('data-listener')) return;
                    card.setAttribute('data-listener', 'true');

                    card.addEventListener('click', function() {
                        var ref = this.getAttribute('data-ref');
                        navigator.clipboard.writeText(ref).then(function() {
                            card.style.background = '#d4edda';
                            card.style.borderColor = '#28a745';
                            setTimeout(function() {
                                card.style.background = 'white';
                                card.style.borderColor = '#ddd';
                            }, 2000);
                        });
                    });

                    card.addEventListener('mouseover', function() {
                        if (this.style.background !== 'rgb(212, 237, 218)') {
                            this.style.background = '#f8f9fa';
                            this.style.borderColor = '#999';
                        }
                    });

                    card.addEventListener('mouseout', function() {
                        if (this.style.background !== 'rgb(212, 237, 218)') {
                            this.style.background = 'white';
                            this.style.borderColor = '#ddd';
                        }
                    });
                });
            }, 500);
        })();
        </script>
        """
        )

        return mark_safe("".join(parts))

    @action(description="Publish selected posts")
    def publish_selected(self, request, queryset):
        """Publish selected posts."""
        from django.utils import timezone

        count = 0
        for post in queryset:
            post.status = "published"
            if not post.published_at:
                post.published_at = timezone.now()
            post.save()
            count += 1
        self.message_user(request, f"Published {count} post(s).")

    @action(description="Unpublish selected posts")
    def unpublish_selected(self, request, queryset):
        """Unpublish selected posts."""
        count = queryset.update(status="draft")
        self.message_user(request, f"Unpublished {count} post(s).")

    @action(description="Feature selected posts")
    def feature_selected(self, request, queryset):
        """Mark selected posts as featured."""
        count = queryset.update(is_featured=True)
        self.message_user(request, f"Featured {count} post(s).")

    @action(description="Unfeature selected posts")
    def unfeature_selected(self, request, queryset):
        """Remove featured status from selected posts."""
        count = queryset.update(is_featured=False)
        self.message_user(request, f"Unfeatured {count} post(s).")

    @action(description="Rebuild backlinks for selected posts")
    def rebuild_backlinks_for_selected(self, request, queryset):
        """Rebuild internal links for selected posts by parsing their content."""
        from engine.links.extractor import update_post_links

        total_stats = {
            'posts_processed': 0,
            'links_created': 0,
            'links_updated': 0,
            'links_deleted': 0,
            'links_failed': 0,
        }

        for post in queryset:
            try:
                stats = update_post_links(post)
                total_stats['posts_processed'] += 1
                total_stats['links_created'] += stats['links_created']
                total_stats['links_updated'] += stats['links_updated']
                total_stats['links_deleted'] += stats['links_deleted']
                total_stats['links_failed'] += stats['links_failed']
            except Exception as e:
                self.message_user(
                    request,
                    f"Error processing '{post.title}': {str(e)}",
                    level=messages.ERROR
                )

        # Show summary
        self.message_user(
            request,
            f"Processed {total_stats['posts_processed']} post(s): "
            f"{total_stats['links_created']} links created, "
            f"{total_stats['links_updated']} updated, "
            f"{total_stats['links_deleted']} deleted.",
            level=messages.SUCCESS
        )

        if total_stats['links_failed'] > 0:
            self.message_user(
                request,
                f"Warning: {total_stats['links_failed']} link(s) failed to resolve.",
                level=messages.WARNING
            )

    @action(description="Export selected posts as CSV")
    def export_posts_csv(self, request, queryset):
        """Export posts as CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="posts_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Title",
                "Slug",
                "Author",
                "Status",
                "Visibility",
                "Published",
                "Word Count",
                "Reading Time",
                "Views",
                "Comments",
                "Likes",
                "Featured",
                "Pinned",
                "Created",
                "Updated",
            ]
        )

        for post in queryset:
            writer.writerow(
                [
                    post.title,
                    post.slug,
                    post.author.username,
                    post.get_status_display(),
                    post.get_visibility_display(),
                    (
                        post.published_at.strftime("%Y-%m-%d %H:%M")
                        if post.published_at
                        else ""
                    ),
                    post.word_count,
                    post.reading_time_minutes,
                    post.view_count,
                    post.comment_count,
                    post.like_count,
                    "Yes" if post.is_featured else "No",
                    "Yes" if post.is_pinned else "No",
                    post.created_at.strftime("%Y-%m-%d %H:%M"),
                    post.updated_at.strftime("%Y-%m-%d %H:%M"),
                ]
            )

        return response


# --------------------------
# Asset Organization Admins
# --------------------------


@admin.register(AssetFolder)
class AssetFolderAdmin(ModelAdmin):
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
                "classes": ["unfold-column-2"],
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

    @display(description="Folder", ordering="path")
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

    @display(description="Assets")
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
class AssetTagAdmin(ModelAdmin):
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

    @display(description="Tag", ordering="name")
    def tag_display(self, obj):
        """Display tag with color badge."""
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; border-radius: 4px; font-weight: 500;">{}</span>',
            obj.color,
            obj.name,
        )

    @display(description="Assets")
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

    @display(description="Preview")
    def color_preview(self, obj):
        """Show color swatch."""
        return format_html(
            '<div style="width: 40px; height: 20px; background: {}; border: 1px solid #dee2e6; border-radius: 3px;"></div>',
            obj.color,
        )


@admin.register(AssetCollection)
class AssetCollectionAdmin(ModelAdmin):
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
                "classes": ["unfold-column-2"],
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

    @display(description="Collection", ordering="name")
    def collection_name_with_cover(self, obj):
        """Display collection with cover image."""
        if obj.cover_asset and obj.cover_asset.asset_type == "image" and obj.cover_asset.file:
            return format_html(
                '<div style="display: flex; align-items: center; gap: 10px;">'
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 6px; border: 1px solid #dee2e6;" />'
                '<div>'
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
            '<div>'
            '<div style="font-weight: 600;">{}</div>'
            '<div style="font-size: 11px; color: #6c757d;">{}</div>'
            "</div>"
            "</div>",
            icon,
            obj.name,
            "Public" if obj.is_public else "Private",
        )

    @display(description="Assets")
    def asset_count_display(self, obj):
        """Display number of assets in collection."""
        count = obj.asset_count()
        if count == 0:
            return format_html(
                '<span style="color: #999; font-style: italic;">No assets yet</span>'
            )
        return format_html(
            '<span style="background: #e7f3ff; color: #004085; padding: 4px 12px; border-radius: 4px; font-weight: 600;">'
            '{} asset{}'
            "</span>",
            count,
            "s" if count != 1 else "",
        )
