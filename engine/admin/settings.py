from django.contrib import admin

from engine.models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
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

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
