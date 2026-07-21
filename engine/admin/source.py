"""
Admin configuration for the Source model (bibliography system).

Provides a rich interface for managing the source library with organized
fieldsets, custom display methods, search, and filtering.
"""

from django.contrib import admin, messages
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from engine.models import Source, SourceFile, UrlStatus

from .display import admin_change_link, mk_pill, muted
from .mixins import SoftDeleteAdminMixin


class CitedFilter(admin.SimpleListFilter):
    """Filter sources by whether any post cites them."""

    title = "cited in posts"
    parameter_name = "cited"

    def lookups(self, request, model_admin):
        return (("yes", "Cited"), ("no", "Uncited"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(post_citations__isnull=False).distinct()
        if self.value() == "no":
            return queryset.filter(post_citations__isnull=True)
        return queryset


class SourceFileInline(admin.TabularInline):
    """Archived files for a source — upload, label, and visibility control."""

    model = SourceFile
    extra = 1
    fields = (
        "file",
        "download_link",
        "kind",
        "label",
        "is_public",
        "provenance",
        "size_display",
        "sha256_short",
    )
    readonly_fields = (
        "download_link",
        "kind",
        "provenance",
        "size_display",
        "sha256_short",
    )

    @admin.display(description="Download")
    def download_link(self, obj):
        if obj.pk and obj.file:
            try:
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener">{}</a>',
                    obj.file.url,
                    obj.original_filename or obj.file.name,
                )
            except ValueError:
                pass
        return "—"

    @admin.display(description="Size")
    def size_display(self, obj):
        if not obj.pk or not obj.size:
            return "—"
        size = float(obj.size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024

    @admin.display(description="SHA-256")
    def sha256_short(self, obj):
        if obj.pk and obj.sha256:
            return format_html("<code>{}</code>", obj.sha256[:12])
        return "—"


@admin.register(Source)
class SourceAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    class Media:
        css = {"all": ("css/admin-common.css",)}

    inlines = [SourceFileInline]

    change_form_template = "admin/engine/source/change_form.html"

    list_display = (
        "citation_key_display",
        "title_truncated",
        "first_author_display",
        "year_display",
        "source_type_display",
        "url_status_display",
        "cited_count_display",
        "is_deleted",
        "created_at",
    )
    list_display_links = ("citation_key_display",)
    list_filter = (
        "source_type",
        "url_status",
        CitedFilter,
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
            "Citations",
            {
                "fields": ("cited_in_posts",),
                "description": "Posts whose content cites this source "
                "(derived from [@key] references).",
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
        "cited_in_posts",
        "url_last_checked",
        "url_check_count",
        "zotero_version",
        "zotero_raw",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_cited_count=Count("post_citations", distinct=True))
        )

    # -- Custom display methods --

    @admin.display(description="Cited", ordering="_cited_count")
    def cited_count_display(self, obj):
        count = getattr(obj, "_cited_count", None)
        if count is None:
            count = obj.post_citations.count()
        return count if count else muted("0")

    @admin.display(description="Cited in")
    def cited_in_posts(self, obj):
        """Linked list of posts citing this source, with their status."""
        if not obj or not obj.pk:
            return muted("Save the source first.")
        citations = obj.post_citations.select_related("post").order_by("post__title")
        if not citations:
            return muted("Not cited in any post yet.")
        rows = format_html_join(
            "",
            '<li style="margin-bottom:2px;">{} {}</li>',
            (
                (
                    admin_change_link(pc.post, pc.post.title),
                    mk_pill(
                        pc.post.get_status_display(),
                        "success" if pc.post.status == "published" else "muted",
                        size="sm",
                    ),
                )
                for pc in citations
            ),
        )
        return format_html('<ul style="margin:0;padding-left:1.2em;">{}</ul>', rows)

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

    # -- Per-object change-form buttons --

    def response_change(self, request, obj):
        """Handle the extra change-form buttons (fetch metadata / check URL).

        These run synchronously so the author sees fields fill in on the
        reload — unlike the bulk changelist actions, which queue on Celery.
        The regular form save has already happened by the time this runs.
        """
        if "_fetch_doi" in request.POST:
            return self._fetch_and_redirect(request, obj, "doi")
        if "_fetch_url" in request.POST:
            return self._fetch_and_redirect(request, obj, "url")
        if "_check_url" in request.POST:
            return self._check_url_and_redirect(request, obj)
        return super().response_change(request, obj)

    def _fetch_and_redirect(self, request, obj, resolve_type):
        from engine.bibliography.metadata_resolvers import (
            apply_metadata_to_source,
            resolve_doi,
            resolve_url,
        )

        value = getattr(obj, resolve_type, "")
        if not value:
            messages.warning(
                request,
                f"This source has no {resolve_type.upper()} to fetch from.",
            )
            return HttpResponseRedirect(request.path)

        resolver = resolve_doi if resolve_type == "doi" else resolve_url
        try:
            csl_data = resolver(value)
        except Exception:
            csl_data = None
        if not csl_data:
            messages.error(request, f"Could not fetch metadata for {value}.")
            return HttpResponseRedirect(request.path)

        updated = apply_metadata_to_source(obj, csl_data)
        if updated:
            obj.save()
            messages.success(
                request,
                f"Filled from {resolve_type.upper()}: {', '.join(updated)}.",
            )
        else:
            messages.info(request, "No empty fields to fill — nothing was changed.")
        return HttpResponseRedirect(request.path)

    def _check_url_and_redirect(self, request, obj):
        from engine.bibliography.link_checker import (
            check_url,
            check_wayback_machine,
        )

        if not obj.url:
            messages.warning(request, "This source has no URL to check.")
            return HttpResponseRedirect(request.path)

        result = check_url(obj.url)
        status = result["status"]
        archive_url = obj.url_archive
        if status == "broken":
            archive_url = check_wayback_machine(obj.url) or archive_url
            if archive_url and archive_url != obj.url_archive:
                status = "archived"
        Source.objects.filter(pk=obj.pk).update(
            url_status=status,
            url_last_checked=timezone.now(),
            url_check_count=obj.url_check_count + 1,
            url_archive=archive_url,
        )
        level = messages.SUCCESS if status in ("ok", "redirect") else messages.WARNING
        messages.add_message(
            request, level, f"URL check complete: status is “{status}”."
        )
        return HttpResponseRedirect(request.path)

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
