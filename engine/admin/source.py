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
    class Media:
        css = {"all": ("css/admin-common.css",)}

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
        pill_class = {
            UrlStatus.OK: "mk-pill--success",
            UrlStatus.REDIRECT: "mk-pill--warn",
            UrlStatus.BROKEN: "mk-pill--danger",
            UrlStatus.ARCHIVED: "mk-pill--info",
            UrlStatus.UNCHECKED: "mk-pill--muted",
        }.get(obj.url_status, "mk-pill--muted")
        return format_html(
            '<span class="mk-pill {}">{}</span>',
            pill_class,
            obj.get_url_status_display(),
        )

    # -- Admin actions --
    #
    # These fetch external URLs (DOI/CrossRef, arbitrary web pages, the Zotero
    # API), each up to the resolver timeout. Running them inline would time out
    # the admin request for anything but a tiny selection, so they are queued on
    # Celery; results land on the sources and in Task Results / the Celery
    # status page. The .delay() is guarded so a dead broker reports an error
    # instead of 500-ing the action.

    def _queue(self, request, task, *args, queued_msg=""):
        try:
            task.delay(*args)
        except Exception as exc:  # broker unreachable
            self.message_user(
                request,
                f"Could not queue background task (broker unreachable?): {exc}",
                level=messages.ERROR,
            )
            return False
        self.message_user(request, queued_msg, level=messages.SUCCESS)
        return True

    def _queue_metadata_fetch(self, request, queryset, resolve_type, exclude_field):
        from engine.bibliography.tasks import fetch_metadata_for_source

        ids = list(queryset.exclude(**{exclude_field: ""}).values_list("pk", flat=True))
        try:
            for pk in ids:
                fetch_metadata_for_source.delay(pk, resolve_type)
        except Exception as exc:  # broker unreachable
            self.message_user(
                request,
                f"Could not queue task (broker unreachable?): {exc}",
                level=messages.ERROR,
            )
            return
        self.message_user(
            request,
            f"Queued {resolve_type.upper()} metadata fetch for {len(ids)} "
            "source(s). Results appear on the sources shortly (see Task Results).",
            level=messages.SUCCESS,
        )

    @admin.action(description="Fetch metadata from DOI (background)")
    def fetch_metadata_from_doi(self, request, queryset):
        self._queue_metadata_fetch(request, queryset, "doi", "doi")

    @admin.action(description="Fetch metadata from URL (background)")
    def fetch_metadata_from_url(self, request, queryset):
        self._queue_metadata_fetch(request, queryset, "url", "url")

    @admin.action(description="Check URLs for availability (background)")
    def check_urls(self, request, queryset):
        from engine.bibliography.tasks import check_source_urls_for_ids

        ids = list(queryset.exclude(url="").values_list("pk", flat=True))
        self._queue(
            request,
            check_source_urls_for_ids,
            ids,
            queued_msg=f"Queued URL availability check for {len(ids)} source(s). "
            "Statuses update shortly (see Task Results).",
        )

    @admin.action(description="Sync selected from Zotero (background re-import)")
    def sync_from_zotero(self, request, queryset):
        from engine.bibliography.tasks import resync_zotero_sources

        ids = list(queryset.exclude(zotero_key="").values_list("pk", flat=True))
        self._queue(
            request,
            resync_zotero_sources,
            ids,
            queued_msg=f"Queued Zotero re-import for {len(ids)} source(s). "
            "Results appear shortly (see Task Results).",
        )
