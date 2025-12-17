"""Admin configuration for Page model."""

from django.contrib import admin

from engine.models import Page, PageFeaturedTag


class PageFeaturedTagInline(admin.TabularInline):
    """Inline admin for featured tags on a page."""

    model = PageFeaturedTag
    extra = 1
    autocomplete_fields = ["tag"]
    fields = ["tag", "display_title", "order"]
    ordering = ["order"]


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    """Admin for editable static page content."""

    list_display = ["slug", "title", "is_active", "featured_tags_count", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["slug", "title", "content"]
    readonly_fields = ["content_html", "created_at", "updated_at"]
    ordering = ["slug"]
    inlines = [PageFeaturedTagInline]

    fieldsets = [
        (
            None,
            {
                "fields": ["slug", "title", "is_active"],
            },
        ),
        (
            "Content",
            {
                "fields": ["content", "content_html"],
                "description": "Write content in Markdown. HTML is auto-generated.",
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

    def featured_tags_count(self, obj):
        return obj.featured_tags.count()
    featured_tags_count.short_description = "Featured Tags"
