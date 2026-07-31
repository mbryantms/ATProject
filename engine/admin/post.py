"""
Admin classes for Post model and related inlines.

This module contains the admin configuration for posts, including
internal links (backlinks), post-asset relationships, and revision history.
"""

import csv
import difflib
import logging
import re

from django.contrib import admin, messages
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from engine.markdown.cheatsheet import (
    palette_payload as cheatsheet_palette_payload,
)
from engine.markdown.cheatsheet import (
    reference_html as cheatsheet_reference_html,
)
from engine.models import (
    InternalLink,
    Post,
    PostAsset,
    PostCitation,
    PostFurtherReading,
    PostRevision,
    PostSimilarity,
    PostSlugHistory,
)

from .display import admin_change_link
from .mixins import ReadOnlyAdminMixin, SoftDeleteAdminMixin

logger = logging.getLogger(__name__)

# Curated list of CSL styles supported by the citeproc-js bridge.
# Leaving blank uses the site-wide default.
CITATION_STYLE_CHOICES = [
    ("", "— Use site default —"),
    ("chicago-author-date", "Chicago (author-date)"),
    # NB: must match the .csl filename in engine/bibliography/styles/ —
    # "chicago-note-bibliography" (no s) silently fell back to APA.
    ("chicago-notes-bibliography", "Chicago (notes & bibliography)"),
    ("apa", "APA 7th edition"),
    ("modern-language-association", "MLA 9th edition"),
    ("ieee", "IEEE"),
    ("nature", "Nature"),
    ("harvard-cite-them-right", "Harvard (Cite Them Right)"),
    ("vancouver", "Vancouver"),
]

# Static sample renderings to help an author pick a citation style
# without leaving the change form. These are illustrative, not authoritative —
# the real renderer is citeproc-js on the server.
_CITATION_STYLE_SAMPLES = [
    (
        "chicago-author-date",
        "(Smith 2024, 42)",
        "Smith, Jane. 2024. “A Short Article.” Journal of Things 12 (3): 37–58.",
    ),
    (
        "chicago-notes-bibliography",
        "¹ Jane Smith, “A Short Article,”…",
        "Smith, Jane. “A Short Article.” Journal of Things 12, no. 3 (2024): 37–58.",
    ),
    (
        "apa",
        "(Smith, 2024, p. 42)",
        "Smith, J. (2024). A short article. Journal of Things, 12(3), 37–58.",
    ),
    (
        "modern-language-association",
        "(Smith 42)",
        "Smith, Jane. “A Short Article.” Journal of Things, vol. 12, no. 3, 2024, pp. 37–58.",
    ),
    (
        "ieee",
        "[1]",
        "[1] J. Smith, “A short article,” J. Things, vol. 12, no. 3, pp. 37–58, 2024.",
    ),
    (
        "nature",
        "Smith, J. ¹",
        "1. Smith, J. A short article. J. Things 12, 37–58 (2024).",
    ),
    (
        "harvard-cite-them-right",
        "(Smith, 2024)",
        "Smith, J. (2024) ‘A short article’, Journal of Things, 12(3), pp. 37–58.",
    ),
    ("vancouver", "(1)", "1. Smith J. A short article. J Things. 2024;12(3):37–58."),
]


def _build_citation_style_help_html():
    rows = []
    for key, inline, bib in _CITATION_STYLE_SAMPLES:
        label = dict(CITATION_STYLE_CHOICES).get(key, key)
        rows.append(
            f'<div class="mk-cs-entry">'
            f"<h5>{label} <code>{key}</code></h5>"
            f'<div class="mk-cs-sample">Inline: {inline}</div>'
            f'<div class="mk-cs-sample">Bibliography: {bib}</div>'
            f"</div>"
        )
    # The toggle behavior lives in static/js/admin-post-aux.js (loaded via
    # PostAdmin.Media) — an external file so the site's nonce CSP doesn't block
    # it, and so the JS is linted/cached in one place.
    return (
        '<span class="mk-citestyle-help">'
        "<button type='button' class='mk-citestyle-help-btn' "
        "aria-label='Show citation style examples'>?</button>"
        '<div class="mk-citestyle-help-panel" role="dialog">'
        "<strong>Sample output per style</strong>"
        '<div style="margin-top:6px;">' + "".join(rows) + "</div>"
        "</div>"
        "</span>"
    )


CITATION_STYLE_HELP_HTML = _build_citation_style_help_html()

# Regex matching asset references in markdown: @asset:key or @alias used
# inside a markdown link/image target. Mirrors the production
# asset_resolver preprocessor pattern so orphan warnings stay in sync.
_ASSET_REF_RE = re.compile(r"!?\[[^\]]*\]\(@(asset:)?([a-zA-Z0-9_-]+)(?:\?[^\)]*)?\)")


# Fenced-div snippets surfaced in the CM6 editor when a line starts with ``:::``.
# Templates use CM6 snippet syntax (``${n:placeholder}`` / ``$0`` for final cursor).
EDITOR_FENCE_SNIPPETS = [
    {
        "className": "admonition-tip",
        "detail": "Tip callout",
        "template": "::: {.admonition-tip}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "admonition-note",
        "detail": "Neutral note callout",
        "template": "::: {.admonition-note}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "admonition-warning",
        "detail": "Warning callout",
        "template": "::: {.admonition-warning}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "admonition-error",
        "detail": "Error / pitfall callout",
        "template": "::: {.admonition-error}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "epigraph",
        "detail": "Opening epigraph quote",
        "template": "::: {.epigraph}\n> ${1:Quote}\n>\n> --- ${2:Attribution}\n:::\n$0",
    },
    {
        "className": "columns",
        "detail": "Multi-column list",
        "template": "::: {.columns}\n- ${1:item}\n- ${2:item}\n- ${3:item}\n:::\n$0",
    },
    {
        "className": "text-center",
        "detail": "Center-aligned block",
        "template": "::: {.text-center}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "text-right",
        "detail": "Right-aligned block",
        "template": "::: {.text-right}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "sans-serif",
        "detail": "Sans-serif paragraphs",
        "template": "::: {.sans-serif}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "float-left",
        "detail": "Float a block to the left",
        "template": "::: {.float-left}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "float-right",
        "detail": "Float a block to the right",
        "template": "::: {.float-right}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "width-full",
        "detail": "Full-bleed width block",
        "template": "::: {.width-full}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "table-small",
        "detail": "Compact/dense table variant",
        "template": "::: {.table-small}\n| ${1:a} | ${2:b} |\n|---|---|\n| ${3:1} | ${4:2} |\n:::\n$0",
    },
    {
        "className": "sortable",
        "detail": "Client-sortable table",
        "template": "::: {.sortable}\n| ${1:Col 1} | ${2:Col 2} |\n|---|---|\n| ${3:a} | ${4:b} |\n:::\n$0",
    },
]

# Inline class names surfaced when the cursor is inside ``{.``. These apply to
# bracketed spans (``[text]{.smallcaps}``), images/links (``![alt](src){.class}``),
# and fenced divs. Not every class is valid in every context, but that's on the
# author — the list is grouped rough-by-use.
EDITOR_INLINE_CLASSES = [
    # Spans
    {"name": "smallcaps", "detail": "Small caps"},
    {"name": "marginnote", "detail": "Margin note (outer-margin)"},
    {"name": "sidenote", "detail": "Sidebar sidenote"},
    {"name": "tabular-nums", "detail": "Tabular / lined numerals"},
    {"name": "sans-serif", "detail": "Sans-serif run"},
    {"name": "date-since", "detail": "Date + 'N years ago' subscript"},
    {"name": "date-range", "detail": "Date range with duration subscript"},
    {"name": "date-range-since", "detail": "Date range + years since end"},
    # Layout utilities
    {"name": "text-center", "detail": "Center-align"},
    {"name": "text-right", "detail": "Right-align"},
    {"name": "float-left", "detail": "Float left"},
    {"name": "float-right", "detail": "Float right"},
    {"name": "width-full", "detail": "Full-bleed width"},
    {"name": "icon-not", "detail": "Suppress auto link icon"},
    # Fenced-div modifiers
    {"name": "admonition-tip", "detail": "Tip callout"},
    {"name": "admonition-note", "detail": "Note callout"},
    {"name": "admonition-warning", "detail": "Warning callout"},
    {"name": "admonition-error", "detail": "Error callout"},
    {"name": "epigraph", "detail": "Epigraph block"},
    {"name": "columns", "detail": "Multi-column list"},
    {"name": "table-small", "detail": "Compact table"},
    {"name": "sortable", "detail": "Sortable table"},
]


class ContentAssetInline(admin.StackedInline):
    """Shared asset attachment UI for PostAsset and PageAsset."""

    extra = 1
    min_num = 0
    max_num = 50

    autocomplete_fields = ["asset"]
    ordering = ["order"]

    def get_queryset(self, request):
        # Every readonly display method reads obj.asset.* — pull it in one join
        # instead of a query per attached asset row.
        return super().get_queryset(request).select_related("asset")

    # Verbose names for better UX
    verbose_name = "Asset"
    verbose_name_plural = "Content Assets"

    fieldsets = [
        (
            None,
            {
                "fields": (
                    ("asset_preview", "asset"),
                    ("alias", "order", "markdown_ref_display"),
                ),
                "classes": [],
            },
        ),
        (
            "Custom Overrides (Optional)",
            {
                "fields": (
                    ("custom_alt_text", "asset_default_alt"),
                    ("custom_caption", "asset_default_caption"),
                ),
                "classes": ["collapse"],
                "description": "Override default asset metadata for this content item only. The right column shows what will appear on the site if you leave the override blank.",
            },
        ),
    ]

    readonly_fields = [
        "asset_preview",
        "markdown_ref_display",
        "asset_default_alt",
        "asset_default_caption",
    ]

    @admin.display(description="Default alt (fallback)")
    def asset_default_alt(self, obj):
        if not obj or not obj.asset:
            return mark_safe(
                '<div class="mk-override-fallback">Pick an asset first.</div>'
            )
        default = obj.asset.alt_text or ""
        if not default:
            return mark_safe(
                '<div class="mk-override-fallback">'
                '<span class="mk-of-label">No default set</span>'
                "The underlying asset has no <code>alt_text</code>. "
                "Set one here or on the asset itself so screen readers have something to read."
                "</div>"
            )
        return format_html(
            '<div class="mk-override-fallback">'
            '<span class="mk-of-label">Default:</span>{}'
            "</div>",
            default,
        )

    @admin.display(description="Default caption (fallback)")
    def asset_default_caption(self, obj):
        if not obj or not obj.asset:
            return mark_safe(
                '<div class="mk-override-fallback">Pick an asset first.</div>'
            )
        default = obj.asset.caption or ""
        if not default:
            return mark_safe(
                '<div class="mk-override-fallback">'
                '<span class="mk-of-label">No default caption.</span>'
                "Leave blank for no caption, or enter one on the left."
                "</div>"
            )
        return format_html(
            '<div class="mk-override-fallback">'
            '<span class="mk-of-label">Default:</span>{}'
            "</div>",
            default,
        )

    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to improve UX."""
        formset = super().get_formset(request, obj, **kwargs)

        # Make alias not required
        if "alias" in formset.form.base_fields:
            formset.form.base_fields["alias"].required = False
            formset.form.base_fields[
                "alias"
            ].help_text = 'Optional: Short name for this content item (e.g., "fig1")'
            formset.form.base_fields["alias"].widget.attrs.update(
                {"placeholder": "Leave blank to use global key"}
            )

        # Improve order field
        if "order" in formset.form.base_fields:
            formset.form.base_fields[
                "order"
            ].help_text = "Display order (lower numbers first)"

        # Improve custom fields help text
        if "custom_caption" in formset.form.base_fields:
            formset.form.base_fields[
                "custom_caption"
            ].help_text = "Override default caption for this content item only"
            formset.form.base_fields["custom_caption"].widget.attrs.update(
                {"rows": 2, "placeholder": "Leave blank to use asset's default caption"}
            )

        if "custom_alt_text" in formset.form.base_fields:
            formset.form.base_fields[
                "custom_alt_text"
            ].help_text = "Override default alt text for this post only"
            formset.form.base_fields["custom_alt_text"].widget.attrs.update(
                {"placeholder": "Leave blank to use asset's default alt text"}
            )

        return formset

    @admin.display(description="Preview")
    def asset_preview(self, obj):
        """Show enhanced preview in inline (theme-aware)."""
        if not obj or not obj.asset or not obj.asset.file:
            return mark_safe(
                '<div class="mk-ap-card mk-ap-empty">'
                '<span class="mk-ap-icon">📎</span>'
                '<span class="mk-ap-label">No asset</span>'
                "</div>"
            )

        if obj.asset.asset_type == "image":
            return format_html(
                '<div class="mk-ap-img">'
                '<img src="{}" class="mk-ap-img-thumb" />'
                '<div class="mk-ap-dims">{} × {}</div>'
                "</div>",
                obj.asset.file.url,
                obj.asset.width or "?",
                obj.asset.height or "?",
            )

        icons_info = {
            "video": ("🎬", "Video"),
            "audio": ("🎵", "Audio"),
            "document": ("📄", "Document"),
            "archive": ("📦", "Archive"),
            "other": ("📎", "File"),
        }
        icon, label = icons_info.get(obj.asset.asset_type, ("📎", "File"))
        return format_html(
            '<div class="mk-ap-card mk-ap-type-{}">'
            '<span class="mk-ap-icon">{}</span>'
            '<span class="mk-ap-label">{}</span>'
            "</div>",
            obj.asset.asset_type,
            icon,
            label,
        )

    @admin.display(description="Reference")
    def markdown_ref_display(self, obj):
        """Show the markdown reference with a copy button (theme-aware).

        The copy button carries the text in ``data-clipboard-text``; the click
        handler is delegated in static/js/admin-post-aux.js (no inline onclick,
        which the site's nonce CSP would block).
        """
        if not (obj and obj.pk and obj.asset):
            return mark_safe('<code class="mk-inline-ref-code">-</code>')
        ref = f"@{obj.alias}" if obj.alias else f"@asset:{obj.asset.key}"
        return format_html(
            '<div class="mk-inline-ref">'
            '<code class="mk-inline-ref-code">{}</code>'
            '<button type="button" class="mk-inline-ref-copy mk-copy-btn" '
            'data-clipboard-text="{}">Copy</button>'
            "</div>",
            ref,
            ref,
        )


class PostAssetInline(ContentAssetInline):
    model = PostAsset
    verbose_name = "Asset"
    verbose_name_plural = "Post Assets"


class IncomingLinksInline(admin.TabularInline):
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

    def get_queryset(self, request):
        # source_post_link reads obj.source_post.title — avoid a query per row.
        return super().get_queryset(request).select_related("source_post")

    def has_add_permission(self, request, obj=None):
        """Backlinks are auto-generated, not manually added."""
        return False

    @admin.display(description="Source Post")
    def source_post_link(self, obj):
        """Display source post with link to admin."""
        if not obj or not obj.pk:
            return "—"
        return admin_change_link(obj.source_post, obj.source_post.title)


class PostSimilarityInline(admin.TabularInline):
    """Read-only inline showing computed similar posts with component breakdown."""

    model = PostSimilarity
    fk_name = "source_post"
    extra = 0
    max_num = 10
    can_delete = False
    verbose_name = "Similar Post"
    verbose_name_plural = "Similar Posts (auto-computed)"
    fields = ("target_post_link", "score", "components_display", "computed_at")
    readonly_fields = (
        "target_post_link",
        "score",
        "components_display",
        "computed_at",
    )
    ordering = ["-score"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Can't slice here — BaseInlineFormSet.__init__ applies .filter() on
        # the queryset afterward, which errors on sliced querysets. max_num
        # (set on the class) caps the rendered form count instead.
        return super().get_queryset(request).select_related("target_post")

    @admin.display(description="Target Post")
    def target_post_link(self, obj):
        if not obj or not obj.target_post_id:
            return "—"
        return admin_change_link(obj.target_post, obj.target_post.title)

    @admin.display(description="Components")
    def components_display(self, obj):
        if not obj or not obj.components:
            return "—"
        parts = [f"{k}={v}" for k, v in obj.components.items()]
        return format_html("<code>{}</code>", ", ".join(parts))


class PostRevisionInline(admin.TabularInline):
    model = PostRevision
    extra = 0
    can_delete = False
    max_num = 0
    ordering = ["-version"]
    verbose_name = "Revision"
    verbose_name_plural = "Revision History"

    fields = ("version_link", "created_by", "created_at", "size_display")
    readonly_fields = ("version_link", "created_by", "created_at", "size_display")

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Defer the (potentially large) markdown body and compute its length in
        # the database instead. size_display previously called
        # len(obj.content_markdown), which loaded the full body of every
        # historical revision on each change-form open.
        from django.db.models.functions import Length

        return (
            super()
            .get_queryset(request)
            .defer("content_markdown")
            .annotate(_md_len=Length("content_markdown"))
        )

    @admin.display(description="Version")
    def version_link(self, obj):
        if not obj or not obj.pk:
            return "-"
        diff_url = reverse(
            "admin:engine_post_revision_diff", args=[obj.post_id, obj.pk]
        )
        return format_html('<a href="{}">v{}</a>', diff_url, obj.version)

    @admin.display(description="Size")
    def size_display(self, obj):
        if not obj or not obj.pk:
            return "-"
        size = getattr(obj, "_md_len", None)
        if size is None:
            size = len(obj.content_markdown)
        if size < 1024:
            return f"{size} B"
        return f"{size / 1024:.1f} KB"


class PostCitationInline(admin.TabularInline):
    model = PostCitation
    extra = 0
    fields = ("source_display", "position", "annotation")
    readonly_fields = ("source_display", "position")
    ordering = ["position"]
    verbose_name = "Cited Source"
    verbose_name_plural = "Cited Sources"

    def get_queryset(self, request):
        # source_display reads obj.source.* — avoid a query per citation row.
        return super().get_queryset(request).select_related("source")

    @admin.display(description="Source")
    def source_display(self, obj):
        if obj.pk and obj.source:
            return f"{obj.source.citation_key}: {obj.source.title[:60]}"
        return "-"

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Citations are auto-managed from content — don't allow manual deletes
        return False

    # Change permission stays enabled so the per-post ``annotation`` field is
    # editable (annotated bibliographies); source/position remain readonly
    # because the rows themselves are auto-managed from content.


class PostFurtherReadingInline(admin.TabularInline):
    """Curated Further Reading list — fully editable, unlike Cited Sources."""

    model = PostFurtherReading
    extra = 0
    fields = ("source", "position", "note")
    autocomplete_fields = ("source",)
    ordering = ["position"]
    verbose_name = "Further Reading entry"
    verbose_name_plural = "Further Reading (curated)"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("source")


# --------------------------
# Post admin
# --------------------------
@admin.register(Post)
class PostAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    inlines = [
        PostAssetInline,
        PostCitationInline,
        PostFurtherReadingInline,
        IncomingLinksInline,
        PostSimilarityInline,
        PostRevisionInline,
    ]
    save_on_top = True
    date_hierarchy = "published_at"

    class Media:
        js = (
            "js/dist/admin-post-editor.js",
            "js/admin-post-aux.js",
            "js/admin-clipboard.js",
        )
        css = {"all": ("css/admin-common.css", "css/admin-post.css")}

    list_display = (
        "post_title_with_status",
        "author",
        "status_badge",
        "completion_status_badge",
        "visibility_badge",
        "featured_pinned_indicators",
        "show_toc",
        "published_at",
        "stats_compact",
    )

    list_filter = (
        "status",
        "completion_status",
        "visibility",
        "is_featured",
        "is_pinned",
        "show_toc",
        "is_deleted",
        "published_at",
        "created_at",
        "updated_at",
        "categories",
        "tags",
        "series",
        "author",
    )

    # content_markdown is intentionally excluded: admin search does an
    # unindexed ILIKE '%term%' over the full body (the search_vector GIN index
    # can't serve it), which is slow at scale. Body text is searchable through
    # the site's full-text search; these fields identify a post for editing.
    search_fields = ("title", "subtitle", "description", "slug")
    ordering = ("-is_pinned", "pin_order", "-published_at", "-created_at")
    list_select_related = ("author", "series")

    # Autocomplete for every editable relation. (published_by / last_edited_by
    # are readonly audit fields, so they aren't listed here — the autocomplete
    # widget would never render for them. filter_horizontal was also removed:
    # when a field is in autocomplete_fields, Django uses the autocomplete
    # widget and ignores filter_horizontal, so it was dead configuration.)
    autocomplete_fields = (
        "author",
        "co_authors",
        "series",
        "categories",
        "tags",
    )

    # Fields excluded from the form entirely — internal caches and
    # derived columns that the Celery pipeline / DB triggers manage.
    exclude = (
        "content_html_cached",
        "table_of_contents",
        "extras",
        "search_vector",
    )

    readonly_fields = (
        # Content aids
        "markdown_cheatsheet",
        "asset_markdown_reference_helper",
        "cite_picker_controls",
        "preview_controls",
        # Derived metrics
        "word_count",
        "reading_time_minutes",
        "view_count",
        "comment_count",
        "like_count",
        # Audit
        "version",
        "published_by",
        "last_edited_by",
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
        "attach_referenced_assets",
        "regenerate_html_cache",
        "soft_delete_selected",
        "restore_selected",
        "export_posts_csv",
    )

    # Slug from title is handy for editors
    prepopulated_fields = {"slug": ("title",)}

    # Facet counts are opt-in (append ?_facets to the URL). Computing them on
    # every changelist load ran a COUNT per choice across 14 filters (incl. the
    # categories/tags/series/author M2M-FK filters) — ~75 queries per load.
    show_facets = admin.ShowFacets.ALLOW

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        from django import forms as dj_forms
        from django.contrib.admin.widgets import AdminTextareaWidget

        # Make text fields full-width with better editing experience
        if db_field.name == "content_markdown":
            import json as _json

            # Resolve admin URLs once and stamp them onto the widget so the
            # CM6 bootstrap doesn't need to hardcode them.
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 30,
                    "cols": 120,
                    "style": "width: 100%; font-family: monospace; font-size: 16px;",
                    "data-cm-markdown-editor": "1",
                    "data-cm-citations-url": reverse(
                        "admin:engine_post_autocomplete_citations"
                    ),
                    "data-cm-assets-url": reverse(
                        "admin:engine_post_autocomplete_assets"
                    ),
                    "data-cm-upload-url": reverse("admin:engine_post_upload_asset"),
                    "data-cm-asset-info-url": reverse("admin:engine_post_asset_info"),
                    "data-cm-assets-panel-url": reverse(
                        "admin:engine_post_assets_panel"
                    ),
                    "data-cm-update-asset-url": reverse(
                        "admin:engine_post_update_asset"
                    ),
                    "data-cm-attach-asset-url": reverse(
                        "admin:engine_post_attach_asset"
                    ),
                    "data-cm-lint-url": reverse("admin:engine_post_lint_content"),
                    "data-cm-post-id": str(
                        request.resolver_match.kwargs.get("object_id", "")
                    )
                    if getattr(request, "resolver_match", None)
                    else "",
                    "data-cm-owner-type": "post",
                    "data-cm-owner-id": str(
                        request.resolver_match.kwargs.get("object_id", "")
                    )
                    if getattr(request, "resolver_match", None)
                    else "",
                    "data-cm-fence-snippets": _json.dumps(EDITOR_FENCE_SNIPPETS),
                    "data-cm-inline-classes": _json.dumps(EDITOR_INLINE_CLASSES),
                    # Full markdown reference for the in-editor "Markdown helper"
                    # search-and-insert palette (admin-markdown-helper.js).
                    "data-cm-cheatsheet": cheatsheet_palette_payload(),
                }
            )
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Pandoc-flavoured Markdown. See the reference panel above for "
                "admonitions, asset (<code>@asset:key</code>), citation "
                "(<code>[@key]</code>), footnote, and math syntax."
            )
            return formfield
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
        elif db_field.name == "language":
            # Free-typed IETF tag with a datalist of the common choices.
            from .widgets import LANGUAGE_SUGGESTIONS, DatalistTextInput

            kwargs["widget"] = DatalistTextInput(LANGUAGE_SUGGESTIONS)
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        elif db_field.name == "citation_style":
            # Present curated CSL styles as a dropdown without changing the
            # underlying CharField, so unusual styles can still be set via the
            # ORM or a data migration if needed.
            return dj_forms.ChoiceField(
                choices=CITATION_STYLE_CHOICES,
                required=False,
                label=db_field.verbose_name.title(),
                help_text=mark_safe(
                    "Override the site-wide citation style for this post. "
                    "Leave as default unless the post specifically requires a "
                    "different style." + CITATION_STYLE_HELP_HTML
                ),
            )
        elif db_field.name == "certainty":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "How confident are you in the claims? 1 = highly uncertain / "
                "speculative, 10 = confident / well-evidenced."
            )
            return formfield
        elif db_field.name == "importance":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "How important is this post to the archive? 1 = trivial / "
                "ephemeral, 10 = core / canonical."
            )
            return formfield
        elif db_field.name == "completion_status":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Editorial state shown in page metadata: "
                "<strong>Notes</strong> = raw thoughts, "
                "<strong>Draft</strong> = early pass, "
                "<strong>In Progress</strong> = actively revising, "
                "<strong>Finished</strong> = complete, "
                "<strong>Abandoned</strong> = shelved."
            )
            return formfield
        elif db_field.name == "meta_description":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Override the meta description in <code>&lt;head&gt;</code> and "
                "on social cards. If blank, the <em>description</em> field above "
                "is used."
            )
            return formfield
        elif db_field.name == "hero_image_url":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Primary featured image for cards / hero banner. If blank, the "
                "first image attached to this post is used; if there are no "
                "attached images, the site's default OG image is used."
            )
            return formfield
        elif db_field.name == "og_image_url":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Open Graph override — only set this if you want a different "
                "image for social sharing than the hero image. Leave blank to "
                "reuse <em>hero_image_url</em>."
            )
            return formfield
        elif db_field.name == "canonical_url":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "For syndicated / cross-posted content, point here at the "
                "authoritative URL. Blank means this post is the canonical."
            )
            return formfield
        elif db_field.name == "rating":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Optional author self-rating (0.00–9.99). Purely editorial; not "
                "shown to readers unless a template surfaces it."
            )
            return formfield
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_urls(self):
        custom_urls = [
            path(
                "<int:post_id>/revision/<int:revision_id>/diff/",
                self.admin_site.admin_view(self.revision_diff_view),
                name="engine_post_revision_diff",
            ),
            path(
                "<int:post_id>/revision/<int:revision_id>/restore/",
                self.admin_site.admin_view(self.revision_restore_view),
                name="engine_post_revision_restore",
            ),
            path(
                "preview-markdown/",
                self.admin_site.admin_view(self.preview_markdown_view),
                name="engine_post_preview_markdown",
            ),
            path(
                "autocomplete-citations/",
                self.admin_site.admin_view(self.autocomplete_citations_view),
                name="engine_post_autocomplete_citations",
            ),
            path(
                "create-source/",
                self.admin_site.admin_view(self.create_source_view),
                name="engine_post_create_source",
            ),
            path(
                "autocomplete-assets/",
                self.admin_site.admin_view(self.autocomplete_assets_view),
                name="engine_post_autocomplete_assets",
            ),
            path(
                "upload-asset/",
                self.admin_site.admin_view(self.upload_asset_view),
                name="engine_post_upload_asset",
            ),
            path(
                "asset-info/",
                self.admin_site.admin_view(self.asset_info_view),
                name="engine_post_asset_info",
            ),
            path(
                "assets-panel/",
                self.admin_site.admin_view(self.assets_panel_view),
                name="engine_post_assets_panel",
            ),
            path(
                "update-asset/",
                self.admin_site.admin_view(self.update_asset_view),
                name="engine_post_update_asset",
            ),
            path(
                "attach-asset/",
                self.admin_site.admin_view(self.attach_asset_view),
                name="engine_post_attach_asset",
            ),
            path(
                "lint-content/",
                self.admin_site.admin_view(self.lint_content_view),
                name="engine_post_lint_content",
            ),
        ]
        return custom_urls + super().get_urls()

    # ------------------------------------------------------------------
    # CM6 editor support endpoints
    # ------------------------------------------------------------------

    @staticmethod
    def _author_label(authors):
        """Return 'Smith' or 'Smith & Jones' or 'Smith et al.' from CSL names."""
        if not authors:
            return ""
        families = [a.get("family") or a.get("literal") or "" for a in authors]
        families = [f for f in families if f]
        if not families:
            return ""
        if len(families) == 1:
            return families[0]
        if len(families) == 2:
            return f"{families[0]} & {families[1]}"
        return f"{families[0]} et al."

    @staticmethod
    def _issued_year(issued_date):
        """Pull the year out of a CSL ``issued_date`` dict, or ''."""
        if not issued_date:
            return ""
        parts = issued_date.get("date-parts") or []
        if parts and parts[0]:
            return str(parts[0][0])
        return ""

    def autocomplete_citations_view(self, request):
        """Return top Source matches for the citation autocomplete."""
        from django.db.models import Q
        from django.http import JsonResponse

        from engine.models import Source

        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"results": []}, status=403)

        q = (request.GET.get("q") or "").strip()
        qs = Source.objects.all()
        if q:
            qs = qs.filter(
                Q(citation_key__istartswith=q)
                | Q(citation_key__icontains=q)
                | Q(title__icontains=q)
            )

        qs = qs.order_by("citation_key")[:20]
        results = [self._source_payload(s) for s in qs]
        return JsonResponse({"results": results})

    @classmethod
    def _source_payload(cls, source):
        """JSON shape shared by the citation autocomplete and create endpoints."""
        return {
            "key": source.citation_key,
            "title": (source.title or "")[:140],
            "author": cls._author_label(source.authors or []),
            "year": cls._issued_year(source.issued_date),
        }

    def create_source_view(self, request):
        """
        Create (or find) a Source from a pasted DOI/URL/ISBN/title, for the
        citation picker's "create & insert" flow. Metadata is resolved
        synchronously so the returned citation key reflects author/year.
        """
        import json

        from django.http import JsonResponse

        from engine.bibliography.metadata_resolvers import (
            apply_metadata_to_source,
            classify_identifier,
            resolve_doi,
            resolve_isbn,
            resolve_url,
        )
        from engine.models import Source

        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Forbidden"}, status=403)
        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)

        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        id_type, value = classify_identifier(payload.get("identifier", ""))
        if not id_type:
            return JsonResponse(
                {"error": "Enter a DOI, URL, ISBN, or title."}, status=400
            )

        # Reuse an existing source rather than creating a duplicate
        existing = {
            "doi": lambda: Source.objects.filter(doi__iexact=value).first(),
            "url": lambda: Source.objects.filter(url=value).first(),
            "isbn": lambda: Source.objects.filter(isbn__iexact=value).first(),
            "title": lambda: Source.objects.filter(title__iexact=value).first(),
        }[id_type]()
        if existing:
            return JsonResponse({**self._source_payload(existing), "existing": True})

        source = Source()
        if id_type == "title":
            source.title = value
        else:
            resolver = {
                "doi": resolve_doi,
                "url": resolve_url,
                "isbn": resolve_isbn,
            }[id_type]
            try:
                csl_data = resolver(value)
            except Exception:
                logger.exception("Metadata resolution failed for %s %s", id_type, value)
                csl_data = None
            if not csl_data:
                label = "URL" if id_type == "url" else id_type.upper()
                return JsonResponse(
                    {"error": f"Could not fetch metadata for that {label}."},
                    status=502,
                )
            apply_metadata_to_source(source, csl_data)
            # Record the identifier itself even if the resolver omitted it
            if id_type == "doi" and not source.doi:
                source.doi = value
            elif id_type == "url" and not source.url:
                source.url = value
            elif id_type == "isbn" and not source.isbn:
                source.isbn = value
            if not source.title:
                source.title = value  # last resort so the row is valid

        source.save()
        return JsonResponse(
            {**self._source_payload(source), "existing": False}, status=201
        )

    def autocomplete_assets_view(self, request):
        """Return asset matches, content-local aliases first then global keys.

        Query params: ``q``, ``owner_type`` (post/page), and ``object_id``.
        ``post_id`` remains accepted for older editor bundles.
        """
        from django.db.models import Q
        from django.http import JsonResponse

        from engine.models import Asset, PageAsset, PostAsset

        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"results": []}, status=403)

        q = (request.GET.get("q") or "").strip()
        owner_type = request.GET.get("owner_type") or "post"
        if owner_type not in {"post", "page"}:
            owner_type = "post"
        object_id = request.GET.get("object_id") or request.GET.get("post_id") or ""

        results = []
        seen = set()

        # Content-local aliases first — these are what authors typically want.
        if object_id:
            try:
                relation_model = PageAsset if owner_type == "page" else PostAsset
                owner_filter = {f"{owner_type}_id": int(object_id)}
                pa_qs = (
                    relation_model.objects.filter(**owner_filter)
                    .select_related("asset")
                    .prefetch_related("asset__renditions")
                )
                if q:
                    pa_qs = pa_qs.filter(
                        Q(alias__icontains=q)
                        | Q(asset__key__icontains=q)
                        | Q(asset__title__icontains=q)
                    )
                for pa in pa_qs.order_by("order")[:20]:
                    if not pa.alias or not pa.asset:
                        continue
                    ref_key = pa.alias
                    if ref_key in seen:
                        continue
                    seen.add(ref_key)
                    results.append(
                        {
                            "key": ref_key,
                            "global": False,
                            "type": pa.asset.asset_type,
                            "title": (pa.asset.title or "")[:140],
                            "thumb": pa.asset.thumbnail_url(prefer_width=200),
                        }
                    )
            except ValueError, TypeError:
                pass

        # Then global asset keys.
        asset_qs = Asset.objects.filter(
            is_deleted=False, status="ready"
        ).prefetch_related("renditions")
        if q:
            asset_qs = asset_qs.filter(Q(key__icontains=q) | Q(title__icontains=q))
        for a in asset_qs.order_by("key")[: 20 - len(results)]:
            if a.key in seen:
                continue
            seen.add(a.key)
            results.append(
                {
                    "key": a.key,
                    "global": True,
                    "type": a.asset_type,
                    "title": (a.title or "")[:140],
                    "thumb": a.thumbnail_url(prefer_width=200),
                }
            )

        return JsonResponse({"results": results})

    def upload_asset_view(self, request):
        """Create an Asset from an editor-uploaded file, no page reload.

        Backs paste/drop upload in the markdown editor: the file becomes a
        ready Asset immediately (the normal save pipeline handles key
        generation, metadata, and renditions), and when ``object_id`` names a
        saved post/page the asset is also attached so it appears in the
        attachment inline on next load. The returned ``markdown`` snippet is
        what the editor inserts at the cursor; the ``@asset:key`` reference
        resolves globally, so no attachment or post save is required first.

        POST multipart fields: ``file`` (required), ``title`` (optional,
        defaults to the filename stem), ``owner_type`` (post/page),
        ``object_id`` (optional pk of a saved owner).
        """
        import os

        from django.core.exceptions import ValidationError
        from django.http import JsonResponse

        from engine.api.views import get_asset_type, validate_file_size
        from engine.models import Asset, Page, PageAsset, PostAsset

        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Forbidden"}, status=403)

        uploaded = request.FILES.get("file")
        if uploaded is None:
            return JsonResponse({"error": "No file provided"}, status=400)

        try:
            for validator in Asset._meta.get_field("file").validators:
                validator(uploaded)
        except ValidationError:
            ext = os.path.splitext(uploaded.name)[1] or "(none)"
            return JsonResponse(
                {"error": f"File type {ext} is not allowed"}, status=400
            )

        asset_type = get_asset_type(uploaded.name, uploaded.content_type)
        is_valid, error_message = validate_file_size(uploaded.size, asset_type)
        if not is_valid:
            return JsonResponse({"error": error_message}, status=400)

        title = (request.POST.get("title") or "").strip()
        if not title:
            title = os.path.splitext(os.path.basename(uploaded.name))[0][:255]

        asset = Asset.objects.create(
            file=uploaded,
            title=title,
            uploaded_by=request.user,
        )

        # Attach to the owning post/page when it already exists, so the asset
        # shows up in the attachment inline; a missing/unsaved owner is fine —
        # the global @asset:key reference works without it.
        owner_type = request.POST.get("owner_type") or "post"
        if owner_type not in {"post", "page"}:
            owner_type = "post"
        object_id = request.POST.get("object_id") or ""
        attached = False
        if object_id:
            try:
                if owner_type == "page":
                    owner = Page.objects.get(pk=int(object_id))
                    PageAsset.objects.get_or_create(page=owner, asset=asset)
                else:
                    owner = Post.objects.get(pk=int(object_id))
                    PostAsset.objects.get_or_create(post=owner, asset=asset)
                attached = True
            except ValueError, TypeError, Post.DoesNotExist, Page.DoesNotExist:
                pass

        reference = f"@asset:{asset.key}"
        if asset.asset_type == "image":
            markdown = f"![]({reference})"
        else:
            markdown = f"[{asset.title}]({reference})"

        return JsonResponse(
            {
                "key": asset.key,
                "asset_type": asset.asset_type,
                "title": asset.title,
                "attached": attached,
                "markdown": markdown,
            }
        )

    @staticmethod
    def _resolve_ref(ref, owner_type, object_id):
        """Resolve an editor reference token to (asset, relation_row).

        ``ref`` is what follows ``@`` in the markdown: ``asset:key`` for a
        global reference or a bare token that is tried as an owner-local
        alias first, then as a global key — the same order the markdown
        resolver uses. Returns (None, None) when nothing matches.
        """
        from engine.models import Asset, PageAsset, PostAsset

        relation_model = PageAsset if owner_type == "page" else PostAsset
        owner_field = f"{owner_type}_id"

        content_row = None
        asset = None
        key = ref.removeprefix("asset:")
        is_global = ref.startswith("asset:")

        if not is_global and object_id:
            try:
                content_row = (
                    relation_model.objects.filter(
                        **{owner_field: int(object_id)}, alias=key
                    )
                    .select_related("asset")
                    .first()
                )
            except ValueError, TypeError:
                content_row = None
            if content_row:
                asset = content_row.asset

        if asset is None:
            asset = Asset.objects.filter(
                key=key, is_deleted=False, status="ready"
            ).first()

        if asset is not None and content_row is None and object_id:
            try:
                content_row = (
                    relation_model.objects.filter(
                        **{owner_field: int(object_id)}, asset=asset
                    )
                    .select_related("asset")
                    .first()
                )
            except ValueError, TypeError:
                content_row = None

        return asset, content_row

    @staticmethod
    def _asset_info_payload(asset, content_row):
        """Serialize one asset for the hover card / drawer entries."""
        renditions = list(asset.renditions.all())
        completed = sum(1 for r in renditions if r.status == "completed")
        alt_text = asset.alt_text
        caption = asset.caption
        if content_row:
            alt_text = content_row.custom_alt_text or alt_text
            caption = content_row.custom_caption or caption
        return {
            "key": asset.key,
            "alias": (content_row.alias if content_row else "") or "",
            "title": asset.title,
            "asset_type": asset.asset_type,
            "status": asset.status,
            "thumb": asset.thumbnail_url(prefer_width=400),
            "width": asset.width,
            "height": asset.height,
            "alt_text": alt_text or "",
            "caption": caption or "",
            "attached": content_row is not None,
            "renditions": {"completed": completed, "total": len(renditions)},
            "focal_point_x": asset.focal_point_x,
            "focal_point_y": asset.focal_point_y,
        }

    def asset_info_view(self, request):
        """Resolve one editor reference to asset metadata for the hover card.

        GET params: ``ref`` (the token after ``@`` — ``asset:key`` or a bare
        alias/key), plus ``owner_type``/``object_id`` for alias resolution
        and per-post overrides. 404s with JSON when nothing resolves, which
        the editor renders as an "unknown reference" card.
        """
        from django.http import JsonResponse

        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Forbidden"}, status=403)

        ref = (request.GET.get("ref") or "").strip()
        if not ref:
            return JsonResponse({"error": "ref required"}, status=400)
        owner_type = request.GET.get("owner_type") or "post"
        if owner_type not in {"post", "page"}:
            owner_type = "post"
        object_id = request.GET.get("object_id") or ""

        asset, content_row = self._resolve_ref(ref, owner_type, object_id)
        if asset is None:
            return JsonResponse({"error": "Unknown asset reference"}, status=404)

        return JsonResponse(self._asset_info_payload(asset, content_row))

    def assets_panel_view(self, request):
        """Data for the editor's asset drawer.

        GET params: ``owner_type``/``object_id`` (for the "this post" tab and
        attachment flags), ``q`` (key/title search), ``type`` (asset_type
        filter), ``offset`` (library paging). Returns ``attached`` (the
        owner's attachment rows, in order) and one page of ``library``
        (ready assets, newest first, 30 per page) with ``library_total``.
        """
        from django.db.models import Q
        from django.http import JsonResponse

        from engine.models import Asset, PageAsset, PostAsset

        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Forbidden"}, status=403)

        owner_type = request.GET.get("owner_type") or "post"
        if owner_type not in {"post", "page"}:
            owner_type = "post"
        object_id = request.GET.get("object_id") or ""
        q = (request.GET.get("q") or "").strip()
        type_filter = (request.GET.get("type") or "").strip()
        try:
            offset = max(0, int(request.GET.get("offset") or 0))
        except ValueError, TypeError:
            offset = 0

        attached = []
        attached_asset_ids = set()
        if object_id:
            relation_model = PageAsset if owner_type == "page" else PostAsset
            try:
                rows = (
                    relation_model.objects.filter(
                        **{f"{owner_type}_id": int(object_id)}
                    )
                    .select_related("asset")
                    .prefetch_related("asset__renditions")
                    .order_by("order", "created_at")
                )
                for row in rows:
                    if row.asset is None:
                        continue
                    attached_asset_ids.add(row.asset_id)
                    attached.append(self._asset_info_payload(row.asset, row))
            except ValueError, TypeError:
                pass

        library_qs = Asset.objects.filter(
            is_deleted=False, status="ready"
        ).prefetch_related("renditions")
        if q:
            library_qs = library_qs.filter(Q(key__icontains=q) | Q(title__icontains=q))
        if type_filter:
            library_qs = library_qs.filter(asset_type=type_filter)
        library_qs = library_qs.order_by("-created_at")

        total = library_qs.count()
        page = library_qs[offset : offset + 30]
        library = []
        for asset in page:
            payload = self._asset_info_payload(asset, None)
            payload["attached"] = asset.pk in attached_asset_ids
            library.append(payload)

        return JsonResponse(
            {"attached": attached, "library": library, "library_total": total}
        )

    def update_asset_view(self, request):
        """Edit asset metadata from the drawer, no page reload.

        POST fields: ``key`` (required) plus any of ``title``, ``alt_text``,
        ``caption``, ``focal_point_x``, ``focal_point_y``. Edits apply to the
        Asset itself (site-wide defaults); per-post overrides remain in the
        attachment inline. Returns the refreshed info payload.
        """
        from django.http import JsonResponse

        from engine.models import Asset

        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Forbidden"}, status=403)

        key = (request.POST.get("key") or "").strip()
        asset = Asset.objects.filter(key=key, is_deleted=False).first()
        if asset is None:
            return JsonResponse({"error": "Unknown asset"}, status=404)

        update_fields = []
        if "title" in request.POST:
            title = request.POST["title"].strip()
            if not title:
                return JsonResponse({"error": "Title cannot be empty"}, status=400)
            asset.title = title[:255]
            update_fields.append("title")
        if "alt_text" in request.POST:
            asset.alt_text = request.POST["alt_text"].strip()[:255]
            update_fields.append("alt_text")
        if "caption" in request.POST:
            asset.caption = request.POST["caption"].strip()
            update_fields.append("caption")
        for field in ("focal_point_x", "focal_point_y"):
            if field in request.POST:
                raw = request.POST[field].strip()
                if raw == "":
                    setattr(asset, field, None)
                else:
                    try:
                        value = float(raw)
                    except ValueError:
                        return JsonResponse(
                            {"error": f"{field} must be a number"}, status=400
                        )
                    if not 0.0 <= value <= 1.0:
                        return JsonResponse(
                            {"error": f"{field} must be between 0 and 1"},
                            status=400,
                        )
                    setattr(asset, field, value)
                update_fields.append(field)

        if not update_fields:
            return JsonResponse({"error": "No fields to update"}, status=400)

        asset.save(update_fields=update_fields + ["updated_at"])
        return JsonResponse(self._asset_info_payload(asset, None))

    def attach_asset_view(self, request):
        """Attach an existing asset to a saved post/page from the drawer.

        POST fields: ``key``, ``owner_type``, ``object_id``. Idempotent.
        """
        from django.http import JsonResponse

        from engine.models import Asset, Page, PageAsset, PostAsset

        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Forbidden"}, status=403)

        key = (request.POST.get("key") or "").strip()
        asset = Asset.objects.filter(key=key, is_deleted=False).first()
        if asset is None:
            return JsonResponse({"error": "Unknown asset"}, status=404)

        owner_type = request.POST.get("owner_type") or "post"
        if owner_type not in {"post", "page"}:
            owner_type = "post"
        object_id = request.POST.get("object_id") or ""
        try:
            if owner_type == "page":
                owner = Page.objects.get(pk=int(object_id))
                row, _ = PageAsset.objects.get_or_create(page=owner, asset=asset)
            else:
                owner = Post.objects.get(pk=int(object_id))
                row, _ = PostAsset.objects.get_or_create(post=owner, asset=asset)
        except ValueError, TypeError, Post.DoesNotExist, Page.DoesNotExist:
            return JsonResponse({"error": "Unknown owner"}, status=404)

        return JsonResponse(self._asset_info_payload(asset, row))

    def lint_content_view(self, request):
        """Return CM6-compatible diagnostics for the submitted content.

        Diagnostics carry absolute character offsets (``from`` / ``to``) into
        the source text plus severity + message, matching the shape of
        ``@codemirror/lint`` ``Diagnostic``. Detection lives in
        :mod:`engine.markdown.lint`, shared with the preview modal and the
        save-time warnings so all three stay in sync.
        """
        from django.http import JsonResponse

        from engine.markdown.lint import lint_markdown, to_diagnostics

        if request.method != "POST":
            return JsonResponse({"diagnostics": []}, status=405)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"diagnostics": []}, status=403)

        content = request.POST.get("content", "")
        owner_type = request.POST.get("owner_type") or "post"
        if owner_type not in {"post", "page"}:
            owner_type = "post"
        object_id = request.POST.get("object_id") or request.POST.get("post_id") or ""

        owner = None
        if object_id:
            try:
                if owner_type == "page":
                    from engine.models import Page

                    owner = Page.objects.prefetch_related("page_assets__asset").get(
                        pk=int(object_id)
                    )
                else:
                    owner = Post.all_objects.prefetch_related("post_assets__asset").get(
                        pk=int(object_id)
                    )
            except ValueError, TypeError, ObjectDoesNotExist:
                pass

        relation = None
        if owner is not None:
            relation = getattr(owner, "page_assets", None) or getattr(
                owner, "post_assets", None
            )
        content_assets = (
            list(relation.select_related("asset").all()) if relation else []
        )
        findings = lint_markdown(
            content,
            post_assets=content_assets,
            current_post_pk=owner.pk if owner else None,
        )
        return JsonResponse({"diagnostics": to_diagnostics(findings)})

    # Site CSS files loaded inside the preview iframe. Matches the set
    # included by templates/base.html so rendered posts look close to the
    # real site within the admin modal.
    _PREVIEW_CSS_FILES = (
        "css/dist/base.css",
        "css/dist/colors.css",
        "css/dist/link-icons.css",
        "css/dist/image-focus.css",
        "css/dist/bibliography.css",
    )

    def preview_markdown_view(self, request):
        """Render markdown through the full pipeline for admin preview.

        Accepts POST with ``content`` (markdown text) and optional
        ``post_id`` so post-scoped alias resolution works for drafts that
        haven't been saved yet. Returns JSON ``{ok, html, lint}`` where
        ``html`` is a complete document (HTML + site CSS links) suitable
        for iframe ``srcdoc`` and ``lint`` is a list of warning strings.
        """
        from django.http import JsonResponse
        from django.templatetags.static import static

        from engine.markdown.lint import lint_markdown, summarize
        from engine.markdown.renderer import render_markdown

        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "POST required"}, status=405)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

        content = request.POST.get("content", "")
        owner_type = request.POST.get("owner_type") or "post"
        if owner_type not in {"post", "page"}:
            owner_type = "post"
        object_id = request.POST.get("object_id") or request.POST.get("post_id")

        context = {}
        owner = None
        if object_id:
            try:
                if owner_type == "page":
                    from engine.models import Page

                    owner = Page.objects.prefetch_related(
                        "page_assets__asset", "further_reading__source"
                    ).get(pk=int(object_id))
                    context["content_object"] = owner
                    context["first_line_caps"] = owner.first_line_caps
                else:
                    owner = Post.all_objects.prefetch_related("post_assets__asset").get(
                        pk=int(object_id)
                    )
                    context["post"] = owner
                    context["content_object"] = owner
            except ValueError, TypeError, ObjectDoesNotExist:
                pass

        relation = None
        if owner is not None:
            relation = getattr(owner, "page_assets", None) or getattr(
                owner, "post_assets", None
            )
        content_assets = (
            list(relation.select_related("asset").all()) if relation else []
        )
        findings = lint_markdown(
            content,
            post_assets=content_assets,
            current_post_pk=owner.pk if owner else None,
        )
        lint_items = summarize(findings)

        # The full pipeline (pandoc + postprocessors) is expensive; repeated
        # previews of unchanged content render once. Keyed on owner too —
        # alias resolution differs per post.
        import hashlib

        from django.core.cache import cache as render_cache

        digest = hashlib.sha256(
            f"{owner_type}:{object_id}:{content}".encode()
        ).hexdigest()
        cache_key = f"admin-preview:{digest}"
        rendered = render_cache.get(cache_key)

        if rendered is None:
            try:
                rendered = render_markdown(content, context=context)
            except Exception as exc:
                return JsonResponse(
                    {"ok": False, "error": f"Render failed: {exc}", "lint": lint_items},
                    status=500,
                )
            render_cache.set(cache_key, rendered, 900)

        css_links = "\n".join(
            f'<link rel="stylesheet" href="{static(path)}">'
            for path in self._PREVIEW_CSS_FILES
        )
        iframe_doc = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"{css_links}"
            "<style>body{margin:0;padding:24px 28px;}"
            ".admin-preview-banner{font:12px/1.4 system-ui,sans-serif;"
            "color:#555;background:#f4f4f4;border:1px solid #ddd;"
            "padding:6px 10px;border-radius:4px;margin-bottom:14px;}"
            "</style></head>"
            "<body>"
            "<div class='admin-preview-banner'>"
            "Admin preview — site CSS is loaded; MathJax and client-side "
            "enhancements are not."
            "</div>"
            '<div id="markdownBody" class="markdownBody">'
            f"{rendered}"
            "</div></body></html>"
        )

        return JsonResponse({"ok": True, "html": iframe_doc, "lint": lint_items})

    def revision_diff_view(self, request, post_id, revision_id):
        post = get_object_or_404(Post.all_objects, pk=post_id)
        if not self.has_view_permission(request, post):
            raise PermissionDenied
        revision = get_object_or_404(PostRevision, pk=revision_id, post=post)

        # Find the previous revision for diffing
        prev_revision = (
            PostRevision.objects.filter(post=post, version__lt=revision.version)
            .order_by("-version")
            .first()
        )

        left_label = f"v{prev_revision.version}" if prev_revision else "(empty)"
        right_label = f"v{revision.version}"
        left_lines = (
            prev_revision.content_markdown if prev_revision else ""
        ).splitlines(keepends=True)
        right_lines = revision.content_markdown.splitlines(keepends=True)

        diff_html = difflib.HtmlDiff(wrapcolumn=80).make_table(
            left_lines,
            right_lines,
            fromdesc=left_label,
            todesc=right_label,
            context=True,
            numlines=5,
        )

        # All revisions for this post for the sidebar
        all_revisions = PostRevision.objects.filter(post=post).order_by("-version")

        restore_url = reverse(
            "admin:engine_post_revision_restore",
            args=[post_id, revision_id],
        )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Revision diff: {post.title}",
            "post": post,
            "revision": revision,
            "prev_revision": prev_revision,
            "diff_html": mark_safe(diff_html),
            "all_revisions": all_revisions,
            "restore_url": restore_url,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request, "admin/engine/post/revision_diff.html", context
        )

    def revision_restore_view(self, request, post_id, revision_id):
        if request.method != "POST":
            raise Http404
        post = get_object_or_404(Post.all_objects, pk=post_id)
        # Restoring a revision overwrites the post body — require change rights
        # on this object (admin_view only guarantees is_staff).
        if not self.has_change_permission(request, post):
            raise PermissionDenied
        revision = get_object_or_404(PostRevision, pk=revision_id, post=post)

        post.content_markdown = revision.content_markdown
        post.last_edited_by = request.user
        post.save()

        messages.success(
            request,
            f'Restored "{post.title}" to revision v{revision.version}.',
        )
        return HttpResponseRedirect(reverse("admin:engine_post_change", args=[post_id]))

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    ("title", "slug"),
                    ("subtitle", "language"),
                    ("author", "co_authors"),
                    ("description",),
                ),
                "description": (
                    "Title, URL slug, language, and a short description used "
                    "as the teaser on cards and as the meta-description fallback."
                ),
            },
        ),
        (
            "Content",
            {
                "fields": (
                    ("markdown_cheatsheet",),
                    ("content_markdown",),
                    ("preview_controls",),
                    ("cite_picker_controls",),
                    ("asset_markdown_reference_helper",),
                    ("abstract",),
                ),
                "description": (
                    "Write your post content in Pandoc-flavoured Markdown. "
                    "The render pipeline processes it on save; the preview button "
                    "renders it live with site CSS."
                ),
            },
        ),
        (
            "Publishing",
            {
                "fields": (
                    ("status", "visibility"),
                    ("published_at", "expire_at"),
                    ("is_featured", "is_pinned", "pin_order"),
                ),
                "description": (
                    "<strong>Status</strong> is the publication lifecycle "
                    "(draft → scheduled → published → archived) and, with "
                    "<strong>Visibility</strong>, controls whether the post is "
                    "live and who can see it. Scheduled/published posts go live "
                    "at <em>Published at</em>. (Not to be confused with the "
                    "editorial <em>Completion</em> field under Editorial notes, "
                    "which is only a label shown on the page.)"
                ),
            },
        ),
        (
            "Editorial notes",
            {
                "fields": ("completion_status",),
                "classes": ["collapse"],
                "description": (
                    "<strong>Completion</strong> is an editorial label shown in "
                    "the page metadata (Notes / Draft / In Progress / Finished / "
                    "Abandoned). It does <strong>not</strong> affect visibility "
                    "or publication — that's <em>Status</em> above."
                ),
            },
        ),
        (
            "Taxonomy & Relations",
            {
                "fields": (
                    ("series", "series_order"),
                    ("categories", "tags"),
                ),
                "classes": ["collapse"],
                "description": "Categorize this post. Similar posts are computed automatically — see the PostSimilarity inline below.",
            },
        ),
        (
            "Rendering & Metadata",
            {
                "fields": (
                    ("show_toc", "first_line_caps"),
                    ("citation_style",),
                    ("certainty", "importance"),
                    ("allow_comments", "rating"),
                ),
                "classes": ["collapse"],
                "description": (
                    "Per-post rendering toggles, editorial ratings, and "
                    "comment allowance."
                ),
            },
        ),
        (
            "SEO & Social Sharing",
            {
                "fields": (
                    ("meta_description",),
                    ("hero_image_url",),
                    ("og_image_url",),
                    ("canonical_url",),
                    ("noindex",),
                ),
                "classes": ["collapse"],
                "description": (
                    "Override auto-generated SEO / OG metadata. Fallback "
                    "chain for images: og_image_url → hero_image_url → first "
                    "in-content image → site default."
                ),
            },
        ),
        (
            "Metrics",
            {
                "fields": (
                    ("word_count", "reading_time_minutes"),
                    ("view_count", "comment_count", "like_count"),
                ),
                "classes": ["collapse"],
                "description": "Read-only counters. Updated by the render pipeline and views.",
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    ("version",),
                    ("published_by", "last_edited_by"),
                    ("created_at", "updated_at"),
                ),
                "classes": ["collapse"],
                "description": (
                    "Auto-managed provenance. Version bumps when "
                    "content_markdown changes; published_by is stamped on the "
                    "first publish; last_edited_by updates on every admin save."
                ),
            },
        ),
        (
            "System",
            {
                "fields": (("is_deleted", "deleted_at"),),
                "classes": ["collapse"],
                "description": "Soft-delete state.",
            },
        ),
    )

    @admin.display(description="Post", ordering="title")
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

    @admin.display(description="Status", ordering="status")
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

    @admin.display(description="Completion", ordering="completion_status")
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

    @admin.display(description="Visibility", ordering="visibility")
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

    @admin.display(description="Features")
    def featured_pinned_indicators(self, obj):
        """Show featured/pinned indicators."""
        badges = []
        if obj.is_featured:
            badges.append('<span class="mk-pill mk-pill-featured">⭐ FEATURED</span>')
        if obj.is_pinned:
            badges.append(
                f'<span class="mk-pill mk-pill-pin">📌 PIN {obj.pin_order}</span>'
            )
        if not badges:
            return mark_safe('<span class="mk-muted">—</span>')
        return mark_safe(" ".join(badges))

    @admin.display(description="Stats")
    def stats_compact(self, obj):
        """Display compact statistics."""
        return format_html(
            '<div class="mk-stats-compact">'
            "<div>👁️ {} | 💬 {} | ❤️ {}</div>"
            "<div>📖 {}min | {} words</div>"
            "</div>",
            obj.view_count,
            obj.comment_count,
            obj.like_count,
            obj.reading_time_minutes,
            obj.word_count,
        )

    @admin.display(description="Markdown reference")
    def markdown_cheatsheet(self, obj=None):
        """Markdown reference + launcher for the in-editor helper palette.

        Renders a launcher button (wired by ``admin-markdown-helper.js`` to open
        a searchable insert-at-cursor palette) plus the full browsable reference
        as a no-JS fallback. Both are generated from
        :mod:`engine.markdown.cheatsheet`, the single source of truth also stamped
        onto the editor as JSON.
        """
        return mark_safe(
            '<div class="markdown-cheatsheet" data-md-helper-root>'
            '<button type="button" class="mc-launch" data-md-helper-open>'
            "📖 Markdown helper "
            '<span class="mc-launch-hint">search &amp; insert · '
            "<kbd>Ctrl</kbd>/<kbd>⌘</kbd> <kbd>/</kbd></span>"
            "</button>"
            '<details class="mc-fallback">'
            "<summary>Or browse the full reference</summary>"
            + cheatsheet_reference_html()
            + "</details></div>"
        )

    @admin.display(description="Preview")
    def preview_controls(self, obj=None):
        """Render the 'Preview markdown' button + iframe modal skeleton.

        Posts the current textarea contents to
        ``engine_post_preview_markdown`` and injects the returned HTML
        document into an iframe so the production site CSS applies and
        there's no style bleed from the admin.
        """
        post_id = obj.pk if obj and obj.pk else ""
        preview_url = reverse("admin:engine_post_preview_markdown")
        return format_html(
            '<div class="markdown-preview-controls" '
            'data-preview-url="{}" data-owner-type="post" data-owner-id="{}" '
            'data-textarea-id="id_content_markdown">'
            "<button type='button' class='markdown-preview-btn'>"
            "🔍 Preview rendered markdown</button>"
            "<span class='markdown-preview-hint'>"
            "Opens in a modal with the live site's CSS loaded — no save required. "
            "MathJax isn't evaluated in the preview."
            "</span></div>"
            '<div id="markdown-preview-modal" class="markdown-preview-modal">'
            '<div class="mk-panel">'
            '<div class="mk-header">'
            "<strong>Markdown preview</strong>"
            "<button type='button' id='markdown-preview-close' class='mk-close' aria-label='Close'>✕</button>"
            "</div>"
            '<div id="markdown-preview-lint" class="mk-lint"></div>'
            '<iframe id="markdown-preview-iframe" class="mk-iframe" '
            'sandbox="allow-same-origin"></iframe>'
            "</div></div>",
            preview_url,
            post_id,
        )

    @admin.display(description="Insert citation")
    def cite_picker_controls(self, obj=None):
        """Render the citation picker button + modal (Phase 4.1).

        The CM6 bootstrap exposes its view via ``window.__atpPostEditorView``.
        Clicking a row inserts ``[@key]`` at the editor's current cursor.
        """
        citations_url = reverse("admin:engine_post_autocomplete_citations")
        create_url = reverse("admin:engine_post_create_source")
        return format_html(
            '<div class="mk-cite-controls" data-cite-url="{}" data-cite-create-url="{}">'
            "<button type='button' class='mk-cite-picker-btn'>"
            "📚 Browse &amp; insert citation</button>"
            "<span class='mk-cite-picker-hint'>"
            "Keyboard: <code>↑</code>/<code>↓</code> to navigate, "
            "<code>Enter</code> to insert, <code>Esc</code> to close."
            "</span></div>"
            '<div id="mk-cite-modal" class="mk-cite-modal">'
            '<div class="mk-panel">'
            '<div class="mk-header">'
            "<strong>Insert citation</strong>"
            "<button type='button' id='mk-cite-close' class='mk-close' aria-label='Close'>✕</button>"
            "</div>"
            '<div class="mk-search-row">'
            '<input id="mk-cite-search" type="search" '
            'placeholder="Search by key, title, or author…" autocomplete="off">'
            "</div>"
            '<div id="mk-cite-results" class="mk-results"></div>'
            '<div class="mk-cite-create-row">'
            '<input id="mk-cite-create-input" type="text" '
            'placeholder="New source: paste a DOI, URL, ISBN, or title…" '
            'autocomplete="off">'
            "<button type='button' id='mk-cite-create-btn'>➕ Create &amp; insert</button>"
            "</div>"
            '<div id="mk-cite-create-status" class="mk-cite-create-status"></div>'
            '<div class="mk-cite-footer">'
            "Inserts <code>[@key]</code> at the current cursor position in the markdown editor. "
            "Creating a source fetches metadata from CrossRef / Open Library / the page itself."
            "</div></div></div>",
            citations_url,
            create_url,
        )

    @admin.display(description="Asset Markdown References")
    def asset_markdown_reference_helper(self, obj=None):
        """Display assets attached to this post with their markdown references for quick copying."""
        if not obj or not obj.pk:
            return mark_safe(
                '<div class="mk-asset-info">'
                'ℹ️ Asset references will appear here after you save the post and attach assets in the "Post Assets" section below. '
                "Use <code>@asset:key</code> for global references or <code>@alias</code> for post-local aliases inside your markdown."
                "</div>"
            )

        post_assets = obj.post_assets.select_related("asset").order_by("order")
        orphan_html = self._orphan_asset_ref_warning(obj, post_assets)

        if not post_assets.exists():
            no_assets_html = (
                '<div class="mk-asset-none">'
                '⚠️ No assets attached to this post yet. Add assets in the "Post Assets" section below, then save to see their markdown references here.'
                "</div>"
            )
            return mark_safe(orphan_html + no_assets_html)

        parts = []
        parts.append('<div class="mk-asset-list">')
        parts.append(
            format_html(
                '<div class="mk-asset-header">📎 Assets in this Post ({}) — Click to copy:</div>',
                post_assets.count(),
            )
        )
        parts.append('<div class="mk-asset-grid">')

        icons = {
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "document": "📄",
            "archive": "📦",
            "other": "📎",
        }

        for post_asset in post_assets:
            asset = post_asset.asset
            if post_asset.alias:
                ref = "@" + post_asset.alias
                ref_type = "Alias"
            else:
                ref = "@asset:" + asset.key
                ref_type = "Global"

            icon = icons.get(asset.asset_type, "📎")
            display_title = asset.title[:40] if len(asset.title) > 40 else asset.title
            order_badge_html = (
                format_html(
                    '<span class="mk-asset-order-badge">#{}</span>',
                    post_asset.order,
                )
                if post_asset.order
                else ""
            )

            parts.append(
                format_html(
                    '<div class="mk-asset-card" data-ref="{}">'
                    '<div class="mk-meta">{}{} {} • {}</div>'
                    '<div class="mk-title" title="{}">{}</div>'
                    "<code>{}</code>"
                    "</div>",
                    ref,
                    mark_safe(order_badge_html) if order_badge_html else "",
                    icon,
                    asset.asset_type.title(),
                    ref_type,
                    asset.title,
                    display_title,
                    ref,
                )
            )

        parts.append("</div></div>")
        parts.append(
            '<div class="mk-asset-tip">💡 <strong>Tip:</strong> Click any asset card above to copy its markdown reference.</div>'
        )
        # Click-to-copy on the cards (data-ref) is handled by delegation in
        # static/js/admin-post-aux.js — no inline <script> (nonce CSP).
        return mark_safe(orphan_html + "".join(parts))

    def _orphan_asset_ref_warning(self, obj, post_assets):
        """Render HTML listing asset references in content that don't resolve."""
        from engine.markdown.lint import group_labels, lint_markdown

        findings = lint_markdown(
            obj.content_markdown or "",
            post_assets=post_assets,
            current_post_pk=obj.pk,
        )
        orphans = group_labels(findings).get("asset", [])
        if not orphans:
            return ""

        chips = "".join(
            format_html('<span class="mk-orphan-chip">{}</span>', ref)
            for ref in orphans
        )
        return format_html(
            '<div class="mk-asset-orphan">'
            "⚠️ <strong>Unresolved asset references in content:</strong> {}"
            '<div class="mk-hint">'
            "Attach the matching asset below, fix the key/alias, or remove the reference."
            "</div>"
            "</div>",
            mark_safe(chips),
        )

    def _collect_content_lint_messages(self, post):
        """Return a list of (level, message) tuples for save-time lint warnings.

        Derives from the shared :mod:`engine.markdown.lint` engine so the
        warnings surfaced on save match the CodeMirror gutter and the preview
        modal exactly.
        """
        from engine.markdown.lint import lint_markdown, summarize

        content = post.content_markdown or ""
        if not content:
            return []

        post_assets = (
            list(post.post_assets.select_related("asset").all()) if post.pk else []
        )
        findings = lint_markdown(
            content, post_assets=post_assets, current_post_pk=post.pk
        )
        return [(messages.WARNING, line) for line in summarize(findings)]

    def save_model(self, request, obj, form, change):
        # Auto-stamp audit provenance so authors can't forget.
        obj.last_edited_by = request.user
        if obj.status == Post.Status.PUBLISHED and not obj.published_by:
            obj.published_by = request.user

        super().save_model(request, obj, form, change)
        for level, msg in self._collect_content_lint_messages(obj):
            self.message_user(request, msg, level=level)

    def save_related(self, request, form, formsets, change):
        """
        After inlines save, re-render cached HTML if citation annotations or
        Further Reading entries changed. Post.save() only re-renders on
        content changes, so an inline-only edit would otherwise never reach
        the rendered bibliography / Further Reading section.
        """
        super().save_related(request, form, formsets, change)

        def _formset_touched(fs):
            if fs.model is PostCitation:
                return bool(fs.changed_objects)
            if fs.model is PostFurtherReading:
                return bool(fs.new_objects or fs.changed_objects or fs.deleted_objects)
            return False

        if not any(_formset_touched(fs) for fs in formsets):
            return

        from django.db import transaction

        from engine.tasks import update_post_derived_content

        def _enqueue(pk=form.instance.pk):
            try:
                update_post_derived_content.delay(pk)
            except Exception:
                messages.warning(
                    request,
                    "Annotation saved, but the re-render task could not be "
                    "queued (broker unreachable?). The bibliography will "
                    "update on the next content save.",
                )

        transaction.on_commit(_enqueue)

    @admin.action(description="Publish selected posts")
    def publish_selected(self, request, queryset):
        """Publish selected posts (go-live time + publisher via Post.publish)."""
        count = 0
        for post in queryset:
            post.publish(by=request.user)
            count += 1
        self.message_user(request, f"Published {count} post(s).")

    @admin.action(description="Unpublish selected posts")
    def unpublish_selected(self, request, queryset):
        """Unpublish selected posts."""
        count = queryset.update(status="draft")
        self.message_user(request, f"Unpublished {count} post(s).")

    @admin.action(description="Feature selected posts")
    def feature_selected(self, request, queryset):
        """Mark selected posts as featured."""
        count = queryset.update(is_featured=True)
        self.message_user(request, f"Featured {count} post(s).")

    @admin.action(description="Unfeature selected posts")
    def unfeature_selected(self, request, queryset):
        """Remove featured status from selected posts."""
        count = queryset.update(is_featured=False)
        self.message_user(request, f"Unfeatured {count} post(s).")

    @admin.action(description="Rebuild backlinks for selected posts")
    def rebuild_backlinks_for_selected(self, request, queryset):
        """Rebuild internal links for selected posts by parsing their content."""
        from engine.links.extractor import update_post_links

        total_stats = {
            "posts_processed": 0,
            "links_created": 0,
            "links_updated": 0,
            "links_deleted": 0,
            "links_failed": 0,
        }

        for post in queryset:
            try:
                stats = update_post_links(post)
                total_stats["posts_processed"] += 1
                total_stats["links_created"] += stats["links_created"]
                total_stats["links_updated"] += stats["links_updated"]
                total_stats["links_deleted"] += stats["links_deleted"]
                total_stats["links_failed"] += stats["links_failed"]
            except Exception as e:
                self.message_user(
                    request,
                    f"Error processing '{post.title}': {str(e)}",
                    level=messages.ERROR,
                )

        # Show summary
        self.message_user(
            request,
            f"Processed {total_stats['posts_processed']} post(s): "
            f"{total_stats['links_created']} links created, "
            f"{total_stats['links_updated']} updated, "
            f"{total_stats['links_deleted']} deleted.",
            level=messages.SUCCESS,
        )

        if total_stats["links_failed"] > 0:
            self.message_user(
                request,
                f"Warning: {total_stats['links_failed']} link(s) failed to resolve.",
                level=messages.WARNING,
            )

    @admin.action(description="Regenerate HTML cache & table of contents")
    def regenerate_html_cache(self, request, queryset):
        """Re-render content and rebuild the cached HTML + TOC.

        ``Post.save()`` clears the TOC when content changes and the Celery
        pipeline eventually repopulates ``content_html_cached``. This action
        forces that work synchronously for the selected posts, which is
        useful after pipeline changes or a content/asset migration.
        """
        from engine.markdown.extensions.toc_extractor import extract_toc_from_html
        from engine.markdown.renderer import render_markdown

        count = 0
        failed = 0
        for post in queryset:
            try:
                context = {"post": post}
                html = render_markdown(post.content_markdown or "", context=context)
                post.content_html_cached = html
                try:
                    post.table_of_contents = extract_toc_from_html(html) or []
                except Exception:
                    # TOC extraction is best-effort; leave it empty on failure.
                    post.table_of_contents = []
                post.save(update_fields=["content_html_cached", "table_of_contents"])
                count += 1
            except Exception as exc:
                failed += 1
                self.message_user(
                    request,
                    f"Failed to re-render '{post.title}': {exc}",
                    level=messages.ERROR,
                )
        self.message_user(
            request,
            f"Regenerated HTML + TOC for {count} post(s)"
            + (f", {failed} failed." if failed else "."),
            level=messages.SUCCESS if count else messages.WARNING,
        )

    @admin.action(description="Attach @asset: references found in content")
    def attach_referenced_assets(self, request, queryset):
        """Scan each selected post's content for @asset:key / @alias refs
        and create PostAsset rows for any that resolve to real Assets but
        aren't yet attached."""
        from engine.models import Asset

        total_attached = 0
        total_posts = 0
        total_skipped = 0
        unresolved = set()

        for post in queryset:
            content = post.content_markdown or ""
            if not content or "@" not in content:
                continue

            existing_keys = {
                pa.asset.key
                for pa in post.post_assets.select_related("asset").all()
                if pa.asset
            }
            existing_aliases = {
                pa.alias
                for pa in post.post_assets.select_related("asset").all()
                if pa.alias
            }

            candidate_keys = set()
            for m in _ASSET_REF_RE.finditer(content):
                is_global = m.group(1) == "asset:"
                key = m.group(2)
                if is_global:
                    if key not in existing_keys:
                        candidate_keys.add(key)
                else:
                    if key in existing_aliases or key in existing_keys:
                        continue
                    candidate_keys.add(key)

            if not candidate_keys:
                continue

            # Resolve to real Assets in one query.
            found_assets = {
                a.key: a
                for a in Asset.objects.filter(
                    key__in=candidate_keys, is_deleted=False, status="ready"
                )
            }

            # Figure out a starting order offset so we don't collide.
            next_order = post.post_assets.order_by("-order").values_list(
                "order", flat=True
            )[:1]
            next_order = (next_order[0] if next_order else 0) + 1

            post_touched = False
            for key in candidate_keys:
                asset = found_assets.get(key)
                if not asset:
                    unresolved.add(key)
                    total_skipped += 1
                    continue
                PostAsset.objects.create(post=post, asset=asset, order=next_order)
                next_order += 1
                total_attached += 1
                post_touched = True

            if post_touched:
                total_posts += 1

        self.message_user(
            request,
            f"Attached {total_attached} asset(s) across {total_posts} post(s).",
            level=messages.SUCCESS if total_attached else messages.INFO,
        )
        if unresolved:
            self.message_user(
                request,
                "Unresolved keys (no matching ready Asset): "
                + ", ".join(sorted(unresolved)[:25])
                + ("…" if len(unresolved) > 25 else ""),
                level=messages.WARNING,
            )
        if total_skipped and not unresolved:
            self.message_user(
                request,
                f"Skipped {total_skipped} key(s) — likely aliases already set or missing assets.",
                level=messages.INFO,
            )

    @admin.action(description="Export selected posts as CSV")
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
# Internal Links (Backlinks)
# --------------------------
@admin.register(InternalLink)
class InternalLinkAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """
    Read-only admin for viewing internal links between posts.

    These links are automatically generated when posts are saved by parsing
    markdown content. Manual creation/editing is disabled since these must
    stay in sync with actual post content.
    """

    list_display = (
        "link_display",
        "link_count",
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
    )
    list_select_related = ("source_post", "target_post")
    readonly_fields = (
        "source_post",
        "target_post",
        "link_count",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    )
    list_per_page = 100

    fieldsets = (
        (
            "Link Relationship",
            {
                "fields": (
                    ("source_post", "target_post"),
                    "link_count",
                ),
                "description": "Auto-generated from post content. Links are created when a post references another post's slug.",
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

    @admin.display(description="Link", ordering="source_post__title")
    def link_display(self, obj):
        """Display the link relationship."""
        return format_html(
            "{} → {}",
            admin_change_link(obj.source_post, obj.source_post.title[:40]),
            admin_change_link(obj.target_post, obj.target_post.title[:40]),
        )

    @admin.display(description="Type")
    def link_type_badge(self, obj):
        """Display link direction."""
        return mark_safe(
            '<span style="background: #e7f3ff; color: #004085; padding: 4px 8px; '
            'border-radius: 4px; font-size: 10px; font-weight: 500;">Internal Link</span>'
        )


# --------------------------
# Post Revisions
# --------------------------
@admin.register(PostRevision)
class PostRevisionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("post", "version", "created_by", "created_at", "size_display")
    list_filter = ("created_at",)
    list_select_related = ("post", "created_by")
    search_fields = ("post__title",)
    readonly_fields = (
        "post",
        "version",
        "content_markdown",
        "created_by",
        "created_at",
    )
    ordering = ("-created_at",)

    def get_queryset(self, request):
        # Compute the body length in the DB so the changelist's size column
        # doesn't load every revision's full markdown into memory.
        from django.db.models.functions import Length

        return (
            super()
            .get_queryset(request)
            .defer("content_markdown")
            .annotate(_md_len=Length("content_markdown"))
        )

    @admin.display(description="Size")
    def size_display(self, obj):
        size = getattr(obj, "_md_len", None)
        if size is None:
            size = len(obj.content_markdown)
        if size < 1024:
            return f"{size} B"
        return f"{size / 1024:.1f} KB"


# --------------------------
# Post Similarity (auto-computed)
# --------------------------
@admin.register(PostSimilarity)
class PostSimilarityAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only browser over the precomputed similarity table."""

    list_display = ("source_post", "target_post", "score", "computed_at")
    list_filter = ("computed_at",)
    search_fields = (
        "source_post__title",
        "source_post__slug",
        "target_post__title",
        "target_post__slug",
    )
    list_select_related = ("source_post", "target_post")
    readonly_fields = (
        "source_post",
        "target_post",
        "score",
        "components",
        "computed_at",
    )
    list_per_page = 100


@admin.register(PostSlugHistory)
class PostSlugHistoryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only view of former slugs that 301-redirect to their post."""

    list_display = ("old_slug", "post", "created_at")
    search_fields = ("old_slug", "post__title", "post__slug")
    list_select_related = ("post",)
    readonly_fields = ("old_slug", "post", "created_at")
    list_per_page = 100
