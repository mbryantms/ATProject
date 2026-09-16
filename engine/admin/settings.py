from django import forms
from django.contrib import admin
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.safestring import mark_safe

from engine.markdown import dropcaps
from engine.models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    class Media:
        # admin-post-aux.js + admin-post.css power the citation-style "?"
        # sample panel reused on this page.
        js = ("js/admin-post-aux.js",)
        css = {"all": ("css/admin-common.css", "css/admin-post.css")}

    list_display = ("__str__", "show_edit_buttons", "enable_scheduled_publishing")
    fieldsets = (
        (
            "Behavior",
            {
                "fields": ("show_edit_buttons", "enable_scheduled_publishing"),
            },
        ),
        (
            "SEO & Social",
            {
                "fields": (
                    "site_name",
                    "site_description",
                    "site_url",
                    "default_og_image_url",
                    "twitter_handle",
                ),
                "description": "Site-wide defaults for search engines and social sharing.",
            },
        ),
        (
            "Bibliography",
            {
                "fields": ("default_citation_style",),
                "description": "Default citation formatting style for all posts.",
            },
        ),
        (
            "Typography",
            {
                "fields": ("default_dropcap_style",),
                "description": (
                    "Dropcap on the opening paragraph of every post and page. "
                    "Off unless set here; each post or page can pick its own "
                    "style or switch it off. Authors can also mark any "
                    "paragraph with <code>::: {.dropcap-STYLE}</code>."
                ),
            },
        ),
        (
            "Zotero Integration",
            {
                "fields": (
                    "zotero_library_id",
                    "zotero_library_type",
                    "zotero_api_key",
                    "zotero_last_sync_version",
                    "zotero_last_sync_at",
                ),
                "classes": ("collapse",),
                "description": "Configure Zotero sync. Get an API key at zotero.org/settings/keys.",
            },
        ),
    )
    readonly_fields = ("zotero_last_sync_version", "zotero_last_sync_at")

    def get_urls(self):
        custom = [
            path(
                "dropcap-gallery/",
                self.admin_site.admin_view(self.dropcap_gallery_view),
                name="engine_sitesettings_dropcap_gallery",
            ),
        ]
        return custom + super().get_urls()

    def dropcap_gallery_view(self, request):
        """Every dropcap style rendered in real body text, on the site's own
        stylesheets, so what the picker's tile hints at can be judged in
        context. Standalone document (site CSS restyles the page root, so it
        cannot sit inside the admin chrome)."""
        sample = (
            "wandered lonely as a cloud that floats on high o'er vales and "
            "hills, when all at once I saw a crowd, a host, of golden "
            "daffodils; beside the lake, beneath the trees, fluttering and "
            "dancing in the breeze. Continuous as the stars that shine and "
            "twinkle on the milky way, they stretched in never-ending line "
            "along the margin of a bay."
        )
        quote = (
            "e look before and after, and pine for what is not: our "
            "sincerest laughter with some pain is fraught; our sweetest songs "
            "are those that tell of saddest thought.\u201d"
        )
        context = {
            "site_title": self.admin_site.site_title,
            "back_url": reverse("admin:engine_sitesettings_changelist"),
            "groups": dropcaps.grouped_styles(),
            "style_count": len(dropcaps.STYLES),
            "sample_letter": "I",
            "sample_rest": " " + sample,
            "quote_letter": "W",
            "quote_rest": quote,
        }
        return render(request, "admin/engine/dropcap_gallery.html", context)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "default_dropcap_style":
            from .widgets import DropcapPickerSelect

            kwargs["widget"] = DropcapPickerSelect(
                gallery_url=reverse("admin:engine_sitesettings_dropcap_gallery")
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "default_citation_style":
            # Same curated dropdown the post admin uses, so the site-wide
            # default can't be a typo'd style name that silently falls back
            # to APA. The empty choice IS that fallback, labeled honestly.
            from .post import CITATION_STYLE_CHOICES, CITATION_STYLE_HELP_HTML

            choices = [("", "— apa (built-in fallback) —")] + [
                c for c in CITATION_STYLE_CHOICES if c[0]
            ]
            return forms.ChoiceField(
                choices=choices,
                required=False,
                initial=db_field.default,
                label=db_field.verbose_name.title(),
                help_text=mark_safe(
                    "Default CSL style for every post without an override."
                    + CITATION_STYLE_HELP_HTML
                ),
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
