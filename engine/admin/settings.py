from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe

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

    def formfield_for_dbfield(self, db_field, request, **kwargs):
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
