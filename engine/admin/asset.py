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

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from engine.models import (
    Asset,
    AssetCollection,
    AssetFolder,
    AssetMetadata,
    AssetRendition,
    AssetTag,
    PostAsset,
)

from .mixins import SoftDeleteAdminMixin


def _status_pill_class(status: str) -> str:
    """Map Asset.Status values to shared .mk-pill tone classes."""
    return {
        "uploading": "mk-pill--info",
        "processing": "mk-pill--info",
        "ready": "mk-pill--success",
        "failed": "mk-pill--danger",
        "archived": "mk-pill--muted",
    }.get(status, "")


def _rendition_pill_class(status: str) -> str:
    """Map AssetRendition.Status values to shared .mk-pill tone classes."""
    return {
        "pending": "mk-pill--muted",
        "processing": "mk-pill--warn",
        "completed": "mk-pill--success",
        "failed": "mk-pill--danger",
    }.get(status, "")


class BulkEditAssetsForm(forms.Form):
    """Intermediate form for bulk-editing selected assets.

    Fields left blank are ignored. Tag mode picks how tags are merged.
    """

    TAG_MODE_CHOICES = [
        ("skip", "Leave tags unchanged"),
        ("add", "Add these tags"),
        ("replace", "Replace tags with these"),
        ("remove", "Remove these tags"),
    ]

    alt_text = forms.CharField(required=False, max_length=255)
    credit = forms.CharField(required=False, max_length=255)
    license = forms.CharField(required=False, max_length=100)
    status = forms.ChoiceField(
        required=False,
        choices=[("", "— leave unchanged —")] + list(Asset.Status.choices),
    )
    is_public = forms.ChoiceField(
        required=False,
        choices=[("", "— leave unchanged —"), ("1", "Public"), ("0", "Not public")],
    )
    asset_folder = forms.ModelChoiceField(
        queryset=AssetFolder.objects.all().order_by("path"),
        required=False,
        empty_label="— leave unchanged —",
    )
    clear_folder = forms.BooleanField(
        required=False,
        label="Clear folder (remove asset from any folder)",
    )
    asset_tags = forms.ModelMultipleChoiceField(
        queryset=AssetTag.objects.all().order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    tag_mode = forms.ChoiceField(
        choices=TAG_MODE_CHOICES, initial="skip", required=True
    )


# --------------------------
# Inline classes
# --------------------------
class AssetMetadataInline(admin.StackedInline):
    """Inline for extended asset metadata (OneToOne relationship)."""

    model = AssetMetadata
    can_delete = False
    verbose_name = "Extended Metadata"
    verbose_name_plural = "Extended Metadata"

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
        return _gps_map_html(obj)

    @admin.display(description="Color Preview")
    def color_preview_display(self, obj):
        return _color_preview_html(obj)


def _gps_map_html(obj):
    if not obj.has_gps:
        return mark_safe('<em class="mk-muted">No GPS data available</em>')
    maps_url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"
    return format_html(
        '<div class="mk-gps-card">'
        "<div>📍 {:.6f}, {:.6f}</div>"
        '<a href="{}" target="_blank">🗺️ View on Google Maps</a>'
        "</div>",
        obj.latitude,
        obj.longitude,
        maps_url,
    )


def _color_preview_html(obj):
    if not obj.average_color and not obj.dominant_colors:
        return mark_safe('<em class="mk-muted">No color data available</em>')

    parts = []
    if obj.average_color:
        parts.append(
            format_html(
                '<div class="mk-color-row">'
                '<div class="mk-color-swatch" style="background:{};"></div>'
                '<div><strong>Average:</strong> <code class="mk-code">{}</code></div>'
                "</div>",
                obj.average_color,
                obj.average_color,
            )
        )
    if obj.dominant_colors and isinstance(obj.dominant_colors, list):
        swatches = []
        for color in obj.dominant_colors[:8]:
            if isinstance(color, str) and color.startswith("#"):
                swatches.append(
                    format_html(
                        '<div class="mk-color-swatch mk-color-swatch--sm" '
                        'style="background:{};" title="{}"></div>',
                        color,
                        color,
                    )
                )
        if swatches:
            parts.append(
                format_html(
                    '<div style="margin-top:8px;">'
                    '<div style="font-weight:500;margin-bottom:4px;">Dominant colors:</div>'
                    '<div class="mk-color-strip">{}</div></div>',
                    mark_safe("".join(swatches)),
                )
            )
    if not parts:
        return mark_safe('<em class="mk-muted">No color preview available</em>')
    return mark_safe("".join(parts))


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
                '<img src="{}" class="mk-rendition-thumb" alt="" />',
                obj.file.url,
            )
        return "-"

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        return obj.human_file_size


class PostAssetInline(admin.TabularInline):
    """Inline for per-post usage with editable alias / caption / alt-text overrides."""

    model = PostAsset
    fk_name = "asset"
    extra = 0
    fields = ("post", "alias", "custom_alt_text", "custom_caption", "order")
    autocomplete_fields = ("post",)
    verbose_name = "Post usage"
    verbose_name_plural = "Post usage (per-post aliases / overrides)"
    ordering = ("post__title",)
    classes = ["collapse"]


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

    # ------------------------------------------------------------------
    # Phase 5.1 — richer autocomplete: include asset type + short title in
    # the dropdown text so authors can tell items apart without opening the
    # change page. The underlying ``__str__`` is unchanged so other places
    # that rely on it aren't affected.
    # ------------------------------------------------------------------
    def autocomplete_view(self, request):
        from django.contrib.admin.views.autocomplete import AutocompleteJsonView

        type_icons = {
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "document": "📄",
            "archive": "📦",
            "other": "📎",
        }

        class EnrichedAutocompleteJsonView(AutocompleteJsonView):
            def serialize_result(self, obj, to_field_name):
                icon = type_icons.get(getattr(obj, "asset_type", ""), "📎")
                title = (getattr(obj, "title", "") or "").strip()
                key = getattr(obj, "key", "") or ""
                type_label = obj.get_asset_type_display() if hasattr(obj, "get_asset_type_display") else ""
                bits = [f"{icon} {title}" if title else f"{icon} (no title)"]
                suffix = []
                if type_label:
                    suffix.append(type_label)
                if key:
                    suffix.append(key)
                if suffix:
                    bits.append(" — " + " · ".join(suffix))
                return {
                    "id": str(getattr(obj, to_field_name)),
                    "text": "".join(bits),
                }

        return EnrichedAutocompleteJsonView.as_view(model_admin=self)(request)

    # Performance optimization
    list_select_related = ["uploaded_by"]
    list_per_page = 50

    show_facets = admin.ShowFacets.ALWAYS

    readonly_fields = [
        "preview_large",
        "key_preview",
        "metadata_status_detailed",
        "processing_state",
        "duplicate_warning",
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
            "Asset",
            {
                "fields": [
                    "preview_large",
                    ("title", "status"),
                    ("asset_type",),
                    "file",
                    ("key", "key_preview"),
                ],
                "classes": [],
                "description": "Core info. Leave the key blank to auto-generate it from the title.",
            },
        ),
        (
            "Accessibility & description",
            {
                "fields": [
                    "alt_text",
                    "caption",
                    "description",
                ],
                "classes": [],
                "description": "Required for images. Alt text is read aloud by screen readers and shown if the image fails to load.",
            },
        ),
        (
            "Organization",
            {
                "fields": [
                    "asset_folder",
                    "asset_tags",
                    ("is_public", "uploaded_by"),
                ],
                "classes": [],
                "description": "Where this asset lives and who can see it.",
            },
        ),
        (
            "Markdown reference",
            {
                "fields": [
                    "markdown_reference_copyable",
                    "markdown_usage_examples",
                ],
                "classes": ["collapse"],
                "description": "Copy these into a post's markdown to embed the asset.",
            },
        ),
        (
            "Processing & renditions",
            {
                "fields": ["processing_state"],
                "classes": ["collapse"],
                "description": "Metadata extraction, rendition generation, and recent Celery task results for this asset.",
            },
        ),
        (
            "Attribution & licensing",
            {
                "fields": [
                    ("credit", "license"),
                    "source_url",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Image settings",
            {
                "fields": [
                    ("focal_point_x", "focal_point_y"),
                ],
                "classes": ["collapse"],
                "description": "Focal point coordinates (0.0-1.0) for smart cropping.",
            },
        ),
        (
            "File metadata",
            {
                "fields": [
                    "metadata_status_detailed",
                    ("file_size", "file_extension", "mime_type"),
                    ("width", "height"),
                    ("duration", "bitrate", "frame_rate"),
                    ("original_filename", "file_hash"),
                ],
                "classes": ["collapse"],
                "description": "Auto-populated on upload. Use the <em>Populate metadata (dimensions, MIME type, file size)</em> admin action on the changelist to refresh.",
            },
        ),
        (
            "Duplicates",
            {
                "fields": ["duplicate_warning"],
                "classes": ["collapse"],
                "description": "Other assets sharing this file's SHA256 hash.",
            },
        ),
        (
            "Advanced permissions",
            {
                "fields": ["permissions"],
                "classes": ["collapse"],
                "description": "Raw JSON override for per-asset access rules.",
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
                "classes": ["collapse"],
            },
        ),
        (
            "System",
            {
                "fields": [
                    ("created_at", "updated_at"),
                    ("is_deleted", "deleted_at"),
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    inlines = [AssetMetadataInline, AssetRenditionInline, PostAssetInline]

    class Media:
        css = {"all": ("css/admin-common.css", "css/admin-asset.css")}

    # Default "delete_selected" hard-deletes via queryset.delete() which
    # bypasses the SoftDeleteModel.delete() override. Disable it so authors
    # always go through soft_delete_selected.
    actions = [
        "bulk_edit_assets",
        "populate_metadata",
        "extract_metadata",
        "generate_renditions",
        "generate_video_renditions",
        "update_usage_count",
        "mark_as_ready",
        "mark_as_archived",
        "export_metadata_csv",
        "soft_delete_selected",
        "restore_selected",
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_queryset(self, request):
        """Optimize queryset for list view."""
        qs = super().get_queryset(request)
        # Prefetch related objects to avoid N+1 queries
        qs = qs.prefetch_related("asset_tags", "collections").select_related("asset_folder")
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
                '<div class="mk-asset-row">'
                '<img src="{}" class="mk-asset-row__thumb" alt="" />'
                "<div>"
                '<div class="mk-asset-row__title">{}</div>'
                '<div class="mk-asset-row__meta">{} × {}</div>'
                "</div></div>",
                obj.file.url,
                obj.title,
                obj.width or "?",
                obj.height or "?",
            )
        return format_html(
            '<div class="mk-asset-row">'
            '<div class="mk-asset-row__thumb mk-asset-row__thumb--placeholder">{}</div>'
            '<div class="mk-asset-row__title">{}</div>'
            "</div>",
            icon,
            obj.title,
        )

    @admin.display(description="Key", ordering="key")
    def key_display(self, obj):
        """Display key in compact format."""
        return format_html('<code class="mk-code">{}</code>', obj.key)

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
            '<span class="mk-muted" style="font-size:11px;">{}</span>',
            " • ".join(info) if info else "—",
        )

    @admin.display(description="📋")
    def markdown_key_compact(self, obj):
        """Compact markdown copy button."""
        return format_html(
            "<button type='button' class='mk-copy-btn mk-copy-btn--ghost' "
            "onclick=\"navigator.clipboard.writeText('@asset:{}').then(() => {{ "
            "this.textContent = '✓'; "
            "setTimeout(() => {{ this.textContent = '📋'; }}, 1500); "
            '}}); event.stopPropagation();" '
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
        t = obj.asset_type or "other"
        return format_html(
            '<span class="mk-pill mk-pill--type-{}">{} {}</span>',
            t,
            icons.get(obj.asset_type, ""),
            obj.get_asset_type_display(),
        )

    @admin.display(description="Folder")
    def folder_badge(self, obj):
        """Display asset folder."""
        if not obj.asset_folder:
            return mark_safe('<span class="mk-muted">—</span>')

        depth = obj.asset_folder.path.count("/")
        icon = "📁" if depth > 0 else "📂"

        return format_html(
            '<span class="mk-pill mk-pill--sm mk-pill--folder">{} {}</span>',
            icon,
            obj.asset_folder.name,
        )

    @admin.display(description="Collections")
    def collection_badge(self, obj):
        """Display collections as badges."""
        from django.utils.html import escape

        collections = list(obj.collections.all()[:4])
        if not collections:
            return mark_safe('<span class="mk-muted">—</span>')

        shown = collections[:3]
        badges = [
            f'<span class="mk-pill mk-pill--sm mk-pill--collection">{escape(c.name)}</span>'
            for c in shown
        ]
        if len(collections) > 3:
            remaining = obj.collections.count() - 3
            badges.append(
                f'<span class="mk-muted">+{remaining} more</span>'
            )
        return mark_safe(" ".join(badges))

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        """Display status with appropriate color."""
        return format_html(
            '<span class="mk-pill {}">{}</span>',
            _status_pill_class(obj.status),
            obj.get_status_display(),
        )

    @admin.display(description="Usage", ordering="usage_count")
    def usage_indicator(self, obj):
        """Visual indicator of asset usage."""
        if obj.usage_count == 0:
            return mark_safe('<span class="mk-usage--none">Unused</span>')
        if obj.usage_count <= 3:
            level = "low"
        elif obj.usage_count <= 10:
            level = "med"
        else:
            level = "high"

        return format_html(
            '<strong class="mk-usage--{}">{}</strong> <span class="mk-muted">post{}</span>',
            level,
            obj.usage_count,
            "s" if obj.usage_count != 1 else "",
        )

    @admin.display(description="Asset Preview")
    def preview_large(self, obj):
        """Show full preview in detail view."""
        if obj.asset_type == "image" and obj.file:
            return format_html(
                '<img src="{}" class="mk-asset-preview" alt="" />',
                obj.file.url,
            )
        elif obj.asset_type == "video" and obj.file:
            return format_html(
                '<video controls class="mk-asset-preview mk-asset-preview--video">'
                '<source src="{}" type="{}"></video>',
                obj.file.url,
                obj.mime_type or "video/mp4",
            )
        elif obj.asset_type == "audio" and obj.file:
            return format_html(
                '<audio controls class="mk-asset-preview mk-asset-preview--audio">'
                '<source src="{}" type="{}"></audio>',
                obj.file.url,
                obj.mime_type or "audio/mpeg",
            )
        return format_html(
            '<a href="{}" target="_blank" class="mk-btn">Download file</a>',
            obj.file.url,
        )

    @admin.display(description="Metadata Status")
    def metadata_status_detailed(self, obj):
        """Display metadata completeness status in detail view."""
        checks = {
            "File size": obj.file_size is not None,
            "MIME type": bool(obj.mime_type),
        }

        if obj.asset_type in ["image", "video"]:
            checks["Width"] = obj.width is not None
            checks["Height"] = obj.height is not None
        if obj.asset_type in ["video", "audio"]:
            checks["Duration"] = obj.duration is not None

        missing = [name for name, present in checks.items() if not present]
        total = len(checks)
        present = total - len(missing)

        if not missing:
            status_html = (
                f'<strong class="mk-meta-complete">✓ Complete</strong> '
                f"({present}/{total} fields)"
            )
        else:
            status_html = (
                f'<strong class="mk-meta-incomplete">⚠ Incomplete</strong> '
                f"({present}/{total} fields)<br>"
                f'<span class="mk-muted">Missing: {", ".join(missing)}</span><br>'
                '<em class="mk-muted">Run the &ldquo;Populate metadata&rdquo; admin action to auto-fill.</em>'
            )

        return mark_safe(status_html)

    @admin.display(description="Processing State")
    def processing_state(self, obj):
        """Summarize async processing state for this asset.

        Reads current DB state (metadata record presence, rendition count,
        asset.status) and recent TaskResult rows keyed by asset pk/key. No
        task IDs are tracked on the model, so this is best-effort, not live.
        """
        rows = []

        # Core asset status badge reuse
        rows.append(
            f'<li>Status: <span class="mk-pill {_status_pill_class(obj.status)}">'
            f"{obj.get_status_display()}</span></li>"
        )

        # Metadata extraction
        has_metadata = (
            obj.pk is not None
            and AssetMetadata.objects.filter(asset=obj).exists()
        )
        if has_metadata:
            rows.append(
                '<li>📋 Extended metadata: <span class="mk-pill mk-pill--success">Extracted</span></li>'
            )
        elif obj.asset_type in ("image", "audio", "document"):
            rows.append(
                '<li>📋 Extended metadata: <span class="mk-pill mk-pill--info">'
                "Not yet extracted</span> — run the <em>Extract metadata</em> action</li>"
            )

        # Renditions (images only)
        if obj.asset_type == "image":
            rendition_count = obj.renditions.count() if obj.pk else 0
            if rendition_count == 0:
                rows.append(
                    '<li>🖼️ Renditions: <span class="mk-pill mk-pill--info">'
                    "None yet</span> — run <em>Generate renditions</em></li>"
                )
            else:
                rows.append(
                    f'<li>🖼️ Renditions: <span class="mk-pill mk-pill--success">'
                    f"{rendition_count} generated</span></li>"
                )

        # Video rendition matrix — one row per (preset, format) so it's
        # obvious which codec/resolution is done vs. in-flight vs. failed.
        if obj.asset_type == "video" and obj.pk:
            video_renditions = list(
                obj.renditions.filter(preset__startswith="video-").order_by(
                    "preset", "format"
                )
            )
            poster_renditions = list(
                obj.renditions.filter(preset="poster").order_by("format")
            )
            if poster_renditions:
                poster_pills = []
                for r in poster_renditions:
                    poster_pills.append(
                        f'<span class="mk-pill {_rendition_pill_class(r.status)}">'
                        f"poster/{r.format}: {r.status}</span>"
                    )
                rows.append(
                    "<li>🎞️ Poster: " + " ".join(poster_pills) + "</li>"
                )
            else:
                rows.append(
                    '<li>🎞️ Poster: <span class="mk-pill mk-pill--info">'
                    "Not yet generated</span></li>"
                )

            if video_renditions:
                vid_pills = []
                for r in video_renditions:
                    label = f"{r.preset.replace('video-', '')}/{r.format}"
                    pill = f'<span class="mk-pill {_rendition_pill_class(r.status)}">{label}: {r.status}</span>'
                    if r.status == "failed" and r.error_message:
                        pill = (
                            f'<span title="{r.error_message[:200]}">{pill}</span>'
                        )
                    vid_pills.append(pill)
                rows.append(
                    "<li>📼 Video renditions: " + " ".join(vid_pills) + "</li>"
                )
            else:
                rows.append(
                    '<li>📼 Video renditions: <span class="mk-pill mk-pill--info">'
                    "None yet</span> — run <em>generate_video_renditions</em></li>"
                )

        # Live Celery status for this asset — reads control.inspect() from
        # the broker, not the database. Surfaces tasks that are currently
        # running against this asset so admins can tell "is the worker
        # actually chewing on this, or is it genuinely stuck?".
        try:
            from .celery_status import active_tasks_for_asset

            live_tasks = active_tasks_for_asset(obj)
        except Exception:
            live_tasks = []
        if live_tasks:
            rows.append("<li>🔄 Running now:<ul>")
            for t in live_tasks:
                rows.append(
                    f'<li><code class="mk-code">{t["task_short_name"]}</code> '
                    f'on <code>{t["worker"]}</code> '
                    f'<small class="mk-muted">(running {t["runtime_human"]})</small></li>'
                )
            rows.append("</ul></li>")

        # Recent TaskResults for this asset (best-effort lookup — result
        # backend is Redis so this is usually empty, but left in for
        # environments that flip CELERY_RESULT_BACKEND to django-db).
        try:
            from django_celery_results.models import TaskResult

            key = obj.key or ""
            recent = TaskResult.objects.filter(
                task_kwargs__icontains=key
            ).order_by("-date_done")[:3] if key else []
            if recent:
                rows.append("<li>Recent tasks:<ul>")
                for tr in recent:
                    short_name = (tr.task_name or "").rsplit(".", 1)[-1]
                    rows.append(
                        f'<li><code class="mk-code">{short_name}</code> — {tr.status} '
                        f'<small class="mk-muted">({tr.date_done:%Y-%m-%d %H:%M})</small></li>'
                    )
                rows.append("</ul></li>")
        except Exception:
            pass

        return mark_safe(
            '<ul class="mk-inline-list">' + "".join(rows) + "</ul>"
        )

    @admin.display(description="Possible duplicates")
    def duplicate_warning(self, obj):
        """Warn if another non-deleted asset shares this file's SHA256 hash."""
        if not obj.pk or not obj.file_hash:
            return mark_safe('<span class="mk-muted">—</span>')

        dupes = (
            Asset.objects.filter(file_hash=obj.file_hash)
            .exclude(pk=obj.pk)
            .only("pk", "key", "title", "created_at")[:5]
        )
        if not dupes:
            return mark_safe(
                '<span class="mk-pill mk-pill--success">Unique</span>'
            )

        from django.urls import reverse

        items = []
        for dupe in dupes:
            url = reverse("admin:engine_asset_change", args=[dupe.pk])
            items.append(
                format_html(
                    '<li><a href="{}">{}</a> <code class="mk-code">{}</code> '
                    '<small class="mk-muted">({:%Y-%m-%d})</small></li>',
                    url,
                    dupe.title or "(untitled)",
                    dupe.key,
                    dupe.created_at,
                )
            )
        header = format_html(
            '<span class="mk-pill mk-pill--warn">'
            "{} duplicate(s) by file hash"
            "</span>",
            len(dupes),
        )
        return mark_safe(
            f'{header}<ul class="mk-inline-list" style="margin-top:6px;">{"".join(items)}</ul>'
        )

    @admin.display(description="Auto-Generated Key Preview")
    def key_preview(self, obj):
        """Show preview of what the auto-generated key will be."""
        if obj.key:
            # Already has a key
            return format_html("<p>✓ Key is set: <code>{}</code></p>", obj.key)

        # Preview what will be generated
        if not obj.title:
            return mark_safe(
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
        preview_key = f"{type_prefix}-{base_slug}"

        return format_html(
            "<p>🔮 Auto-generated key will be: <code>{}</code><br>"
            "<small>Includes: {} + title slug (unique suffix added if needed)</small></p>",
            preview_key,
            f"{type_prefix} prefix",
        )

    @admin.display(description="Markdown Reference")
    def markdown_reference_copyable(self, obj):
        """Copyable markdown reference with copy button."""
        return format_html(
            '<div class="mk-copy-row">'
            '<code class="mk-code">@asset:{}</code>'
            "<button type='button' class='mk-copy-btn' "
            "onclick=\"navigator.clipboard.writeText('@asset:{}').then(() => {{ "
            "const orig = this.textContent; this.textContent = '✓ Copied'; "
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
            '<div class="mk-copy-row" style="margin-top:4px;">'
            '<code class="mk-code">{}</code>'
            "<button type='button' class='mk-copy-btn' "
            "onclick=\"navigator.clipboard.writeText('{}').then(() => {{ "
            "const orig = this.textContent; this.textContent = '✓ Copied'; "
            "setTimeout(() => {{ this.textContent = orig; }}, 2000); "
            '}}); event.preventDefault();">Copy</button>'
            "</div></div>",
            example,
            example,
        )

    @admin.display(description="Usage")
    def usage_list(self, obj):
        """Show list of posts using this asset."""
        usages = obj.post_usages.select_related("post")[:10]
        if not usages:
            return mark_safe('<em class="mk-muted">Not used in any posts</em>')

        from django.urls import reverse
        from django.utils.html import escape

        items = []
        for usage in usages:
            post_url = reverse("admin:engine_post_change", args=[usage.post.pk])
            alias = (
                f' <code class="mk-code">@{escape(usage.alias)}</code>'
                if usage.alias else ""
            )
            items.append(
                f'<li><a href="{post_url}" target="_blank">{escape(usage.post.title)}</a>{alias}</li>'
            )

        total = obj.post_usages.count()
        more = ""
        if total > 10:
            more = f'<p class="mk-muted" style="margin:8px 0 0 0;"><em>…and {total - 10} more</em></p>'

        return mark_safe(
            f'<ul class="mk-inline-list">{"".join(items)}</ul>{more}'
        )

    @admin.action(description="Generate renditions for selected images")
    def generate_renditions(self, request, queryset):
        """Queue rendition generation for the image assets in the selection.

        Async by default; falls back to sync when Celery is unreachable
        (capped at 5 images so the admin request doesn't time out).
        """
        image_ids = list(
            queryset.filter(asset_type="image").values_list("pk", flat=True)
        )
        if not image_ids:
            self.message_user(
                request,
                "No images in the selection — renditions are only generated for images.",
                level=messages.WARNING,
            )
            return

        try:
            from engine.tasks import bulk_generate_renditions

            result = bulk_generate_renditions.delay(image_ids)
            self.message_user(
                request,
                f"Queued rendition generation for {len(image_ids)} image(s). "
                f"Task ID: {result.id}",
                level=messages.SUCCESS,
            )
            return
        except Exception as exc:
            if len(image_ids) > 5:
                self.message_user(
                    request,
                    f"Celery broker unreachable ({exc}); refusing sync "
                    f"generation for {len(image_ids)} images (limit 5).",
                    level=messages.ERROR,
                )
                return
            self.message_user(
                request,
                f"Celery broker unreachable ({exc}); running synchronously.",
                level=messages.WARNING,
            )

        from engine.utils import generate_asset_renditions

        touched = 0
        for asset in queryset.filter(asset_type="image"):
            generate_asset_renditions(asset)
            touched += 1
        self.message_user(
            request, f"Generated renditions for {touched} image(s).",
            level=messages.SUCCESS,
        )

    @admin.action(description="Generate renditions for selected videos (poster + MP4/WebM)")
    def generate_video_renditions(self, request, queryset):
        """Queue poster extraction + MP4/WebM transcoding for the video
        assets in the selection.

        Async by default. There is no synchronous fallback because VP9
        1080p can take tens of minutes per asset — running those inside
        an admin request would time out. If Celery is unreachable, the
        action surfaces an error and does nothing.
        """
        video_ids = list(
            queryset.filter(asset_type="video").values_list("pk", flat=True)
        )
        if not video_ids:
            self.message_user(
                request,
                "No videos in the selection — this action only runs on video assets.",
                level=messages.WARNING,
            )
            return

        try:
            from engine.tasks import (
                extract_video_poster_async,
                generate_video_renditions_async,
            )

            for asset_id in video_ids:
                extract_video_poster_async.delay(asset_id)
                generate_video_renditions_async.delay(asset_id)
        except Exception as exc:
            self.message_user(
                request,
                f"Celery broker unreachable ({exc}); video transcoding is "
                f"async-only and was not started.",
                level=messages.ERROR,
            )
            return

        self.message_user(
            request,
            f"Queued poster extraction + MP4/WebM transcoding for "
            f"{len(video_ids)} video(s). Watch progress at "
            f"Task Results → Live Celery status.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Recount asset usage (reconcile cached counter)")
    def update_usage_count(self, request, queryset):
        """Recompute Asset.usage_count from PostAsset.

        The counter is a denormalized cache; nothing currently keeps it fresh
        on PostAsset save/delete, so run this if you suspect drift.
        """
        touched = 0
        for asset in queryset:
            real = asset.post_usages.count()
            if asset.usage_count != real:
                asset.usage_count = real
                asset.save(update_fields=["usage_count"])
                touched += 1

        self.message_user(
            request,
            f"Reconciled {touched} asset(s); {queryset.count() - touched} already accurate.",
            level=messages.SUCCESS if touched else messages.INFO,
        )

    @admin.action(description="Populate metadata (dimensions, MIME type, file size)")
    def populate_metadata(self, request, queryset):
        """Refresh core file metadata for selected assets.

        Surfaces per-asset errors so issues like missing ffprobe or bad video
        streams aren't silently hidden behind a generic "Success" message.
        """
        from engine.utils import refresh_asset_metadata

        total_updated = 0
        per_asset_errors = []
        no_op_assets = []

        for asset in queryset:
            result = refresh_asset_metadata(asset)
            if result["updated"]:
                asset.save(update_fields=result["updated"])
                total_updated += 1
                self.message_user(
                    request,
                    f"{asset.key}: populated {', '.join(result['updated'])}.",
                    level=messages.SUCCESS,
                )
            elif not result["errors"]:
                no_op_assets.append(asset.key)

            for err in result["errors"]:
                per_asset_errors.append((asset.key, err))

        if no_op_assets:
            self.message_user(
                request,
                f"Nothing to populate on {len(no_op_assets)} asset(s) — all fields "
                f"already present ({', '.join(no_op_assets[:5])}"
                f"{'…' if len(no_op_assets) > 5 else ''}).",
                level=messages.INFO,
            )
        for key, err in per_asset_errors:
            self.message_user(
                request, f"{key}: {err}", level=messages.ERROR
            )
        if not per_asset_errors and total_updated == 0 and not no_op_assets:
            self.message_user(request, "No assets selected.", level=messages.WARNING)

    @admin.action(description="Extract extended metadata (EXIF, audio tags, colors)")
    def extract_metadata(self, request, queryset):
        """Extract extended metadata. Queues via Celery when available; falls
        back to sync execution (capped at 10 assets) when the broker can't be
        reached.
        """
        asset_ids = list(queryset.values_list("pk", flat=True))
        if not asset_ids:
            self.message_user(
                request, "No assets selected.", level=messages.WARNING
            )
            return

        # Try async path first — safe for any batch size.
        try:
            from engine.tasks import bulk_extract_metadata

            result = bulk_extract_metadata.delay(asset_ids)
            self.message_user(
                request,
                f"Queued metadata extraction for {len(asset_ids)} asset(s). "
                f"Task ID: {result.id}",
                level=messages.SUCCESS,
            )
            return
        except Exception as exc:
            # Broker unreachable — fall back to sync, but only for small batches.
            if len(asset_ids) > 10:
                self.message_user(
                    request,
                    f"Celery broker unreachable ({exc}); refusing sync "
                    f"extraction for {len(asset_ids)} assets (limit 10).",
                    level=messages.ERROR,
                )
                return
            self.message_user(
                request,
                f"Celery broker unreachable ({exc}); running synchronously.",
                level=messages.WARNING,
            )

        from engine.metadata_extractor import extract_all_metadata

        successful = skipped = 0
        errors = []
        for asset in queryset:
            try:
                if extract_all_metadata(asset):
                    successful += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors.append(f"{asset.key}: {exc}")

        if successful:
            self.message_user(
                request,
                f"Extracted metadata for {successful} asset(s).",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"Skipped {skipped} asset(s) — no metadata available.",
                level=messages.INFO,
            )
        for err in errors[:5]:
            self.message_user(request, err, level=messages.ERROR)
        if len(errors) > 5:
            self.message_user(
                request,
                f"…and {len(errors) - 5} more errors.",
                level=messages.ERROR,
            )

    @admin.action(description="Bulk edit selected assets…")
    def bulk_edit_assets(self, request, queryset):
        """Intermediate-page bulk edit for common fields.

        POST with `apply=1` applies the changes; otherwise renders the form.
        """
        selected_ids = list(queryset.values_list("pk", flat=True))
        if not selected_ids:
            self.message_user(
                request, "No assets selected.", level=messages.WARNING
            )
            return None

        if request.POST.get("apply"):
            form = BulkEditAssetsForm(request.POST)
            if form.is_valid():
                data = form.cleaned_data
                simple_updates = {}
                for field in ("alt_text", "credit", "license"):
                    if data[field]:
                        simple_updates[field] = data[field]
                if data["status"]:
                    simple_updates["status"] = data["status"]
                if data["is_public"] in ("0", "1"):
                    simple_updates["is_public"] = data["is_public"] == "1"
                if data["clear_folder"]:
                    simple_updates["asset_folder"] = None
                elif data["asset_folder"]:
                    simple_updates["asset_folder"] = data["asset_folder"]

                updated_count = 0
                if simple_updates:
                    updated_count = queryset.update(**simple_updates)

                tag_mode = data["tag_mode"]
                tags = list(data["asset_tags"])
                tag_changes = 0
                if tag_mode != "skip" and (tags or tag_mode == "replace"):
                    for asset in queryset:
                        if tag_mode == "add":
                            asset.asset_tags.add(*tags)
                        elif tag_mode == "replace":
                            asset.asset_tags.set(tags)
                        elif tag_mode == "remove":
                            asset.asset_tags.remove(*tags)
                        tag_changes += 1

                self.message_user(
                    request,
                    f"Updated {updated_count or len(selected_ids)} asset(s)"
                    + (f"; tag changes applied to {tag_changes}." if tag_changes else "."),
                    level=messages.SUCCESS,
                )
                return None
        else:
            form = BulkEditAssetsForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Bulk edit {len(selected_ids)} asset(s)",
            "opts": self.model._meta,
            "form": form,
            "assets": queryset[:20],
            "asset_count": len(selected_ids),
            "selected_ids": selected_ids,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
        }
        return render(request, "admin/engine/asset_bulk_edit.html", context)

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
                "Collections",
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
                    ", ".join(c.name for c in asset.collections.all()),
                    asset.asset_folder.path if asset.asset_folder else "",
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

    def _format_size(self, size_bytes):
        """Format bytes as human-readable size."""
        if size_bytes == 0:
            return "0 B"

        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0

        return f"{size_bytes:.2f} TB"


# --------------------------
# AssetMetadata Admin
# --------------------------
class AssetMetadataAdmin(admin.ModelAdmin):
    """Admin for extended asset metadata.

    Not registered with the sidebar: metadata is exposed inline on Asset.
    Kept as a ModelAdmin subclass for potential future standalone use.
    """

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
        from django.urls import reverse

        change_url = reverse("admin:engine_asset_change", args=[obj.asset.pk])
        if obj.asset.asset_type == "image" and obj.asset.file:
            return format_html(
                '<div class="mk-asset-row">'
                '<img src="{}" class="mk-asset-row__thumb" alt="" />'
                '<a href="{}"><code class="mk-code">{}</code></a></div>',
                obj.asset.file.url,
                change_url,
                obj.asset.key,
            )
        return format_html(
            '<a href="{}"><code class="mk-code">{}</code></a>',
            change_url,
            obj.asset.key,
        )

    @admin.display(description="Metadata Summary")
    def metadata_summary(self, obj):
        """Display compact summary of available metadata."""
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
                f'<span class="mk-color-swatch mk-color-swatch--sm" '
                f'style="background:{obj.average_color};vertical-align:middle;" '
                f'title="{obj.average_color}"></span>'
            )

        if not info_parts:
            return mark_safe('<em class="mk-muted">No metadata</em>')

        return mark_safe(
            f'<div style="font-size:11px;">{" • ".join(info_parts)}</div>'
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
        return _gps_map_html(obj)

    @admin.display(description="Color Preview")
    def color_preview_display(self, obj):
        return _color_preview_html(obj)


# --------------------------
# AssetRendition Admin
# --------------------------
class AssetRenditionAdmin(admin.ModelAdmin):
    """Admin for asset renditions.

    Not registered with the sidebar: renditions are exposed inline on Asset.
    Kept as a ModelAdmin subclass for potential future standalone use.
    """

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
                "classes": ["collapse"],
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
                '<img src="{}" class="mk-rendition-thumb" alt="" />',
                obj.file.url,
            )
        return "-"

    @admin.display(description="Asset")
    def asset_key(self, obj):
        """Display asset key with link."""
        from django.urls import reverse

        return format_html(
            '<a href="{}"><code class="mk-code">{}</code></a>',
            reverse("admin:engine_asset_change", args=[obj.asset.pk]),
            obj.asset.key,
        )

    @admin.display(description="Preset")
    def preset_badge(self, obj):
        """Display preset as badge."""
        if not obj.preset:
            return mark_safe('<span class="mk-muted">—</span>')
        return format_html(
            '<span class="mk-pill mk-pill--sm mk-pill--info">{}</span>',
            obj.preset,
        )

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        return obj.human_file_size

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        """Display status with color."""
        tone_map = {
            "pending": "mk-pill--muted",
            "processing": "mk-pill--info",
            "completed": "mk-pill--success",
            "failed": "mk-pill--danger",
        }
        return format_html(
            '<span class="mk-pill {}">{}</span>',
            tone_map.get(obj.status, "mk-pill--muted"),
            obj.get_status_display(),
        )


# --------------------------
# Asset Organization Admins
# --------------------------
@admin.register(AssetFolder)
class AssetFolderAdmin(admin.ModelAdmin):
    """Admin for asset folder hierarchy."""

    class Media:
        css = {"all": ("css/admin-common.css", "css/admin-asset.css")}

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
        indent = mark_safe("&nbsp;" * (depth * 4))
        icon = "📁" if obj.children.exists() else "📂"

        return format_html(
            "{}{} <strong>{}</strong>",
            indent,
            icon,
            obj.name,
        )

    @admin.display(description="Assets")
    def asset_count_display(self, obj):
        """Display number of assets in folder."""
        count = obj.folder_assets.count()
        if count == 0:
            return mark_safe('<span class="mk-muted">0</span>')
        return format_html(
            '<span class="mk-pill mk-pill--sm mk-pill--info">{}</span>',
            count,
        )


@admin.register(AssetTag)
class AssetTagAdmin(admin.ModelAdmin):
    """Admin for asset tags."""

    class Media:
        css = {"all": ("css/admin-common.css", "css/admin-asset.css")}

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
        """Display tag with color-accent pill (tag color as left border)."""
        return format_html(
            '<span class="mk-pill" style="border-left:3px solid {};">{}</span>',
            obj.color,
            obj.name,
        )

    @admin.display(description="Assets")
    def asset_count_display(self, obj):
        """Display number of assets with this tag."""
        count = obj.tagged_assets.count()
        if count == 0:
            return mark_safe('<span class="mk-muted">0</span>')
        return format_html(
            '<span class="mk-pill mk-pill--sm" style="border-left:3px solid {};">{}</span>',
            obj.color,
            count,
        )

    @admin.display(description="Preview")
    def color_preview(self, obj):
        """Show color swatch."""
        return format_html(
            '<div class="mk-color-swatch mk-color-swatch--sm" style="background:{};"></div>',
            obj.color,
        )


@admin.register(AssetCollection)
class AssetCollectionAdmin(admin.ModelAdmin):
    """Admin for asset collections."""

    class Media:
        css = {"all": ("css/admin-common.css", "css/admin-asset.css")}

    list_display = (
        "collection_name_with_cover",
        "user",
        "asset_count_display",
        "is_public",
        "created_at",
    )
    list_filter = ("is_public", "user", "created_at")
    search_fields = ("name", "description")
    autocomplete_fields = ["user", "cover_asset", "assets"]
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
        visibility = "Public" if obj.is_public else "Private"
        if (
            obj.cover_asset
            and obj.cover_asset.asset_type == "image"
            and obj.cover_asset.file
        ):
            return format_html(
                '<div class="mk-asset-row">'
                '<img src="{}" class="mk-asset-row__thumb" alt="" />'
                '<div><div class="mk-asset-row__title">{}</div>'
                '<div class="mk-asset-row__meta">{}</div></div></div>',
                obj.cover_asset.file.url,
                obj.name,
                visibility,
            )

        icon = "🌍" if obj.is_public else "🔒"
        return format_html(
            '<div class="mk-asset-row">'
            '<div class="mk-asset-row__thumb mk-asset-row__thumb--placeholder">{}</div>'
            '<div><div class="mk-asset-row__title">{}</div>'
            '<div class="mk-asset-row__meta">{}</div></div></div>',
            icon,
            obj.name,
            visibility,
        )

    @admin.display(description="Assets")
    def asset_count_display(self, obj):
        """Display number of assets in collection."""
        count = obj.asset_count()
        if count == 0:
            return mark_safe(
                '<em class="mk-muted">No assets yet</em>'
            )
        return format_html(
            '<span class="mk-pill mk-pill--info">{} asset{}</span>',
            count,
            "s" if count != 1 else "",
        )
