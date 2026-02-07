from django.contrib import admin

from engine.models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "show_edit_buttons")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
