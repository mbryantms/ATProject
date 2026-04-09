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
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
