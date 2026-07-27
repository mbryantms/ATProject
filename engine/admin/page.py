"""Admin configuration for rich, editable Page content."""

import json

from django.contrib import admin, messages
from django.contrib.admin.widgets import AdminTextareaWidget
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from engine.markdown.cheatsheet import palette_payload as cheatsheet_palette_payload
from engine.models import (
    Page,
    PageAsset,
    PageFeaturedCategory,
    PageFeaturedTag,
    PageFurtherReading,
)

from .post import (
    EDITOR_FENCE_SNIPPETS,
    EDITOR_INLINE_CLASSES,
    ContentAssetInline,
    PostAdmin,
)


class PageAssetInline(ContentAssetInline):
    model = PageAsset
    verbose_name = "Asset"
    verbose_name_plural = "Page Assets"


class PageFurtherReadingInline(admin.TabularInline):
    model = PageFurtherReading
    extra = 0
    fields = ("source", "position", "note")
    autocomplete_fields = ("source",)
    ordering = ["position"]
    verbose_name = "Further Reading entry"
    verbose_name_plural = "Further Reading (curated)"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("source")


class PageFeaturedTagInline(admin.TabularInline):
    """Inline admin for featured tags on a page."""

    model = PageFeaturedTag
    extra = 1
    autocomplete_fields = ["tag"]
    fields = ["tag", "display_title", "order"]
    ordering = ["order"]


class PageFeaturedCategoryInline(admin.TabularInline):
    """Inline admin for featured categories on a page."""

    model = PageFeaturedCategory
    extra = 1
    autocomplete_fields = ["category"]
    fields = ["category", "display_title", "order"]
    ordering = ["order"]


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    """Admin for pages, with the same Markdown authoring tools as posts."""

    class Media:
        js = (
            "js/dist/admin-post-editor.js",
            "js/admin-post-aux.js",
            "js/admin-clipboard.js",
        )
        css = {"all": ("css/admin-common.css", "css/admin-post.css")}

    list_display = [
        "slug",
        "title",
        "is_active",
        "show_toc",
        "featured_tags_count",
        "featured_categories_count",
        "updated_at",
    ]
    list_filter = ["is_active", "show_toc", "first_line_caps"]
    search_fields = ["slug", "title", "content"]
    readonly_fields = [
        "markdown_cheatsheet",
        "preview_controls",
        "cite_picker_controls",
        "asset_markdown_reference_helper",
        "created_at",
        "updated_at",
    ]
    ordering = ["slug"]
    inlines = [
        PageAssetInline,
        PageFurtherReadingInline,
        PageFeaturedTagInline,
        PageFeaturedCategoryInline,
    ]
    save_on_top = True

    fieldsets = [
        (
            "Identity",
            {"fields": [("slug", "title"), "is_active"]},
        ),
        (
            "Content",
            {
                "fields": [
                    "markdown_cheatsheet",
                    "content",
                    "preview_controls",
                    "cite_picker_controls",
                    "asset_markdown_reference_helper",
                    ("show_toc", "first_line_caps"),
                ],
                "description": (
                    "Write page content in Pandoc-flavoured Markdown. The same "
                    "rendering pipeline used for posts runs on save."
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name != "content":
            return super().formfield_for_dbfield(db_field, request, **kwargs)

        object_id = ""
        if getattr(request, "resolver_match", None):
            object_id = str(request.resolver_match.kwargs.get("object_id", ""))
        kwargs["widget"] = AdminTextareaWidget(
            attrs={
                "rows": 30,
                "cols": 120,
                "style": "width: 100%; font-family: monospace; font-size: 16px;",
                "data-cm-markdown-editor": "1",
                "data-cm-citations-url": reverse(
                    "admin:engine_post_autocomplete_citations"
                ),
                "data-cm-assets-url": reverse("admin:engine_post_autocomplete_assets"),
                "data-cm-lint-url": reverse("admin:engine_post_lint_content"),
                "data-cm-owner-type": "page",
                "data-cm-owner-id": object_id,
                "data-cm-fence-snippets": json.dumps(EDITOR_FENCE_SNIPPETS),
                "data-cm-inline-classes": json.dumps(EDITOR_INLINE_CLASSES),
                "data-cm-cheatsheet": cheatsheet_palette_payload(),
            }
        )
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        formfield.help_text = (
            "Pandoc-flavoured Markdown with admonitions, asset references, "
            "citations, footnotes, tables, and math."
        )
        return formfield

    @admin.display(description="Markdown reference")
    def markdown_cheatsheet(self, obj=None):
        return PostAdmin.markdown_cheatsheet(self, obj)

    @admin.display(description="Insert citation")
    def cite_picker_controls(self, obj=None):
        return PostAdmin.cite_picker_controls(self, obj)

    @admin.display(description="Preview")
    def preview_controls(self, obj=None):
        page_id = obj.pk if obj and obj.pk else ""
        preview_url = reverse("admin:engine_post_preview_markdown")
        return format_html(
            '<div class="markdown-preview-controls" data-preview-url="{}" '
            'data-owner-type="page" data-owner-id="{}" data-textarea-id="id_content">'
            "<button type='button' class='markdown-preview-btn'>"
            "🔍 Preview rendered markdown</button>"
            "<span class='markdown-preview-hint'>"
            "Opens in a modal with the live site's CSS loaded — no save required. "
            "MathJax isn't evaluated in the preview."
            "</span></div>"
            '<div id="markdown-preview-modal" class="markdown-preview-modal">'
            '<div class="mk-panel"><div class="mk-header">'
            "<strong>Markdown preview</strong>"
            "<button type='button' id='markdown-preview-close' class='mk-close' "
            "aria-label='Close'>✕</button></div>"
            '<div id="markdown-preview-lint" class="mk-lint"></div>'
            '<iframe id="markdown-preview-iframe" class="mk-iframe" '
            'sandbox="allow-same-origin"></iframe></div></div>',
            preview_url,
            page_id,
        )

    @admin.display(description="Asset Markdown References")
    def asset_markdown_reference_helper(self, obj=None):
        if not obj or not obj.pk:
            return mark_safe(
                '<div class="mk-asset-info">'
                "Asset references appear here after the page is saved. Attach "
                "assets below and use <code>@alias</code> or <code>@asset:key</code>."
                "</div>"
            )

        page_assets = list(obj.page_assets.select_related("asset").order_by("order"))
        warnings_html = self._orphan_asset_ref_warning(obj, page_assets)
        if not page_assets:
            return mark_safe(
                warnings_html
                + '<div class="mk-asset-none">⚠️ No assets attached to this page yet.</div>'
            )

        cards = []
        icons = {
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "document": "📄",
            "archive": "📦",
            "other": "📎",
        }
        for page_asset in page_assets:
            asset = page_asset.asset
            ref = f"@{page_asset.alias}" if page_asset.alias else f"@asset:{asset.key}"
            cards.append(
                format_html(
                    '<div class="mk-asset-card" data-ref="{}">'
                    '<div class="mk-meta">{} {} • {}</div>'
                    '<div class="mk-title" title="{}">{}</div><code>{}</code></div>',
                    ref,
                    icons.get(asset.asset_type, "📎"),
                    asset.asset_type.title(),
                    "Alias" if page_asset.alias else "Global",
                    asset.title,
                    asset.title[:40],
                    ref,
                )
            )
        return mark_safe(
            warnings_html
            + '<div class="mk-asset-list"><div class="mk-asset-header">'
            + f"📎 Assets in this Page ({len(page_assets)}) — Click to copy:</div>"
            + '<div class="mk-asset-grid">'
            + "".join(str(card) for card in cards)
            + "</div></div>"
        )

    def _orphan_asset_ref_warning(self, obj, page_assets):
        from engine.markdown.lint import group_labels, lint_markdown

        findings = lint_markdown(obj.content or "", post_assets=page_assets)
        orphans = group_labels(findings).get("asset", [])
        if not orphans:
            return ""
        chips = "".join(
            str(format_html('<span class="mk-orphan-chip">{}</span>', ref))
            for ref in orphans
        )
        return (
            '<div class="mk-asset-orphan">⚠️ <strong>Unresolved asset references '
            f"in content:</strong> {chips}</div>"
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        # Page.save initially runs before its asset and Further Reading inlines.
        # Render once more after those relations are committed so aliases,
        # overrides, and curated recommendations are reflected immediately.
        page = form.instance
        page.save(update_fields=["content_html", "table_of_contents"])

        from engine.markdown.lint import lint_markdown, summarize

        page_assets = list(page.page_assets.select_related("asset").all())
        findings = lint_markdown(page.content or "", post_assets=page_assets)
        for warning in summarize(findings):
            self.message_user(request, warning, level=messages.WARNING)

    @admin.display(description="Featured Tags")
    def featured_tags_count(self, obj):
        return obj.featured_tags.count()

    @admin.display(description="Featured Categories")
    def featured_categories_count(self, obj):
        return obj.featured_categories.count()
