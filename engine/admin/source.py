"""
Admin configuration for the Source model (bibliography system).

Provides a rich interface for managing the source library with organized
fieldsets, custom display methods, search, and filtering.
"""

from django.contrib import admin, messages
from django.utils.html import format_html

from engine.models import Source, UrlStatus

from .mixins import SoftDeleteAdminMixin


@admin.register(Source)
class SourceAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        "citation_key_display",
        "title_truncated",
        "first_author_display",
        "year_display",
        "source_type_display",
        "url_status_display",
        "is_deleted",
        "created_at",
    )
    list_display_links = ("citation_key_display",)
    list_filter = (
        "source_type",
        "url_status",
        "is_deleted",
        "created_at",
    )
    search_fields = (
        "citation_key",
        "title",
        "doi",
        "isbn",
        "url",
        "abstract",
    )
    ordering = ("-created_at",)
    list_per_page = 50
    actions = [
        "soft_delete_selected",
        "restore_selected",
        "fetch_metadata_from_doi",
        "fetch_metadata_from_url",
        "check_urls",
        "sync_from_zotero",
    ]

    fieldsets = (
        (
            "Identity",
            {
                "fields": ("citation_key", "source_type", "title"),
                "description": "Citation key is auto-generated if left blank.",
            },
        ),
        (
            "Authors & Editors",
            {
                "fields": ("authors", "editors", "translators"),
                "description": "Use CSL name format: "
                '[{"family": "Smith", "given": "John"}] or '
                '[{"literal": "World Health Organization"}]',
            },
        ),
        (
            "Publication Details",
            {
                "fields": (
                    "container_title",
                    ("publisher", "publisher_place"),
                    ("volume", "issue"),
                    ("page", "edition"),
                ),
            },
        ),
        (
            "Dates",
            {
                "fields": ("issued_date", "accessed_date"),
                "description": "Use CSL date format: "
                '{"date-parts": [[2024, 3, 15]]}. '
                "Partial dates supported (year-only, year-month).",
            },
        ),
        (
            "Identifiers",
            {
                "fields": ("doi", "isbn", "issn", "pmid", "url"),
            },
        ),
        (
            "Content",
            {
                "fields": ("abstract", "language", "note"),
                "classes": ("collapse",),
            },
        ),
        (
            "File Archive",
            {
                "fields": ("archived_file", "archived_file_hash"),
                "classes": ("collapse",),
            },
        ),
        (
            "URL Health",
            {
                "fields": (
                    "url_status",
                    "url_last_checked",
                    "url_check_count",
                    "url_archive",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Zotero",
            {
                "fields": ("zotero_key", "zotero_version", "zotero_raw"),
                "classes": ("collapse",),
            },
        ),
        (
            "System",
            {
                "fields": ("csl_json", "search_vector"),
                "classes": ("collapse",),
                "description": "Auto-generated fields. CSL-JSON is rebuilt on every save.",
            },
        ),
    )

    readonly_fields = (
        "csl_json",
        "search_vector",
        "archived_file_hash",
        "url_last_checked",
        "url_check_count",
        "zotero_version",
        "zotero_raw",
    )

    # -- Custom display methods --

    @admin.display(description="Key", ordering="citation_key")
    def citation_key_display(self, obj):
        return format_html("<code>{}</code>", obj.citation_key)

    @admin.display(description="Title", ordering="title")
    def title_truncated(self, obj):
        title = obj.title or ""
        if len(title) > 70:
            return f"{title[:70]}..."
        return title

    @admin.display(description="Author")
    def first_author_display(self, obj):
        return obj.first_author or "-"

    @admin.display(description="Year")
    def year_display(self, obj):
        return obj.year or "-"

    @admin.display(description="Type", ordering="source_type")
    def source_type_display(self, obj):
        label = obj.get_source_type_display()
        return label

    @admin.display(description="URL", ordering="url_status")
    def url_status_display(self, obj):
        if not obj.url:
            return "-"
        colors = {
            UrlStatus.OK: "#28a745",
            UrlStatus.REDIRECT: "#ffc107",
            UrlStatus.BROKEN: "#dc3545",
            UrlStatus.ARCHIVED: "#6f42c1",
            UrlStatus.UNCHECKED: "#6c757d",
        }
        color = colors.get(obj.url_status, "#6c757d")
        label = obj.get_url_status_display()
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            label,
        )

    # -- Admin actions --

    @admin.action(description="Fetch metadata from DOI")
    def fetch_metadata_from_doi(self, request, queryset):
        from engine.bibliography.metadata_resolvers import (
            apply_metadata_to_source,
            resolve_doi,
        )

        updated = 0
        for source in queryset.exclude(doi=""):
            csl_data = resolve_doi(source.doi)
            if csl_data:
                fields = apply_metadata_to_source(source, csl_data)
                if fields:
                    source.save()
                    updated += 1

        self.message_user(
            request,
            f"Updated {updated} source(s) from DOI metadata.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Fetch metadata from URL")
    def fetch_metadata_from_url(self, request, queryset):
        from engine.bibliography.metadata_resolvers import (
            apply_metadata_to_source,
            resolve_url,
        )

        updated = 0
        for source in queryset.exclude(url=""):
            csl_data = resolve_url(source.url)
            if csl_data:
                fields = apply_metadata_to_source(source, csl_data)
                if fields:
                    source.save()
                    updated += 1

        self.message_user(
            request,
            f"Updated {updated} source(s) from URL metadata.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Check URLs for availability")
    def check_urls(self, request, queryset):
        from engine.bibliography.link_checker import check_url, check_wayback_machine

        checked = 0
        broken = 0
        for source in queryset.exclude(url=""):
            result = check_url(source.url)
            status = result["status"]

            archive_url = source.url_archive
            if status == "broken":
                archive_url = check_wayback_machine(source.url) or archive_url
                if archive_url and archive_url != source.url_archive:
                    status = "archived"
                broken += 1

            from django.utils import timezone

            Source.objects.filter(pk=source.pk).update(
                url_status=status,
                url_last_checked=timezone.now(),
                url_check_count=source.url_check_count + 1,
                url_archive=archive_url,
            )
            checked += 1

        msg = f"Checked {checked} URL(s)."
        if broken:
            msg += f" {broken} broken."
        self.message_user(request, msg, level=messages.SUCCESS)

    @admin.action(description="Sync selected from Zotero (re-import)")
    def sync_from_zotero(self, request, queryset):
        from engine.bibliography.zotero_sync import (
            _update_source_from_csl,
            get_zotero_client,
        )

        try:
            zot = get_zotero_client()
        except ValueError as e:
            self.message_user(request, str(e), level=messages.ERROR)
            return

        updated = 0
        for source in queryset.exclude(zotero_key=""):
            try:
                items = zot.item(source.zotero_key, format="csljson")
                if items:
                    csl_item = items if isinstance(items, dict) else items[0]
                    _update_source_from_csl(source, csl_item)
                    source.zotero_raw = csl_item
                    source.save()
                    updated += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Error re-importing {source.citation_key}: {e}",
                    level=messages.WARNING,
                )

        self.message_user(
            request,
            f"Re-imported {updated} source(s) from Zotero.",
            level=messages.SUCCESS,
        )
