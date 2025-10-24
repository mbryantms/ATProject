"""
Admin classes for taxonomy models (Tag, TagAlias, Category, Series).

This module contains admin configurations for the taxonomy system, including
tags with their aliases, categories, and series.
"""

import csv

from django.contrib import admin, messages
from django.db import models
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from engine.models import Category, Series, Tag, TagAlias


# --------------------------
# Tag Alias Inline
# --------------------------
class TagAliasInline(admin.TabularInline):
    model = TagAlias
    extra = 1
    fields = ("alias", "slug")
    prepopulated_fields = {"slug": ("alias",)}
    verbose_name = "Tag Alias"
    verbose_name_plural = "Tag Aliases"


# --------------------------
# Tag Admin
# --------------------------
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = (
        "colored_name_display",
        "namespace_display",
        "parent_display",
        "is_active_display",
        "rank_display",
        "usage_count_display",
        "post_count",
        "alias_count_display",
        "children_count_display",
        "created_at",
    )
    list_display_links = ("colored_name_display",)
    list_filter = (
        "is_active",
        "namespace",
        "parent",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "name",
        "slug",
        "namespace",
        "description",
        "aliases__alias",
    )
    ordering = ("-rank", "namespace", "name")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("parent",)
    list_per_page = 50
    actions = [
        "activate_tags",
        "deactivate_tags",
        "update_usage_counts",
        "export_tags_csv",
    ]
    inlines = [TagAliasInline]

    # Organize fields into logical sections
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("name", "slug", "namespace"),
                "description": "Core tag identification and namespace grouping",
            },
        ),
        (
            "Hierarchy",
            {
                "fields": ("parent",),
                "description": "Parent tag for hierarchical organization",
            },
        ),
        (
            "Content",
            {
                "fields": ("description",),
                "description": "Detailed description of what this tag represents",
            },
        ),
        (
            "Visual Styling",
            {
                "fields": ("color", "icon"),
                "description": "Visual appearance in the interface",
            },
        ),
        (
            "State & Ranking",
            {
                "fields": ("is_active", "rank"),
                "description": "Visibility and priority settings",
            },
        ),
        (
            "Metadata",
            {
                "fields": ("usage_count", "created_at", "updated_at"),
                "description": "Automatically tracked information",
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at", "usage_count")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("parent").prefetch_related("children", "aliases").annotate(
            _asset_count=models.Count("posts__post_assets__asset", distinct=True),
            _post_count=models.Count("posts", distinct=True),
            _alias_count=models.Count("aliases", distinct=True),
            _children_count=models.Count("children", distinct=True),
        )

    # Custom display methods
    @admin.display(description="Tag", ordering="name")
    def colored_name_display(self, obj):
        """Display tag name with colored badge and icon."""
        icon_html = ""
        if obj.icon:
            # Support for Material icons or emoji
            if len(obj.icon) <= 2:  # Likely an emoji
                icon_html = f'<span style="margin-right: 6px;">{obj.icon}</span>'
            else:  # Material icon or font-awesome
                icon_html = f'<span class="material-icons" style="font-size: 16px; vertical-align: middle; margin-right: 4px;">{obj.icon}</span>'

        html = f'{icon_html}<span style="display: inline-block; padding: 4px 10px; border-radius: 12px; background-color: {obj.color}; color: white; font-weight: 500; font-size: 13px;">{obj.name}</span>'
        return mark_safe(html)

    @admin.display(description="Namespace", ordering="namespace")
    def namespace_display(self, obj):
        """Display namespace with distinct styling."""
        if not obj.namespace:
            return mark_safe('<span style="color: #999; font-style: italic;">—</span>')
        return mark_safe(
            f'<span style="background-color: #F3F4F6; padding: 2px 8px; border-radius: 4px; '
            f'font-size: 12px; font-weight: 500; color: #374151;">{obj.namespace}</span>'
        )

    @admin.display(description="Parent", ordering="parent__name")
    def parent_display(self, obj):
        """Display parent tag with link."""
        if not obj.parent:
            return mark_safe('<span style="color: #999; font-style: italic;">Root</span>')
        return mark_safe(
            f'<a href="/admin/engine/tag/{obj.parent.pk}/change/" style="color: #3B82F6; font-weight: 500;">{obj.parent.name}</a>'
        )

    @admin.display(description="Active", ordering="is_active", boolean=True)
    def is_active_display(self, obj):
        """Display active status as boolean icon."""
        return obj.is_active

    @admin.display(description="Rank", ordering="rank")
    def rank_display(self, obj):
        """Display rank with visual indicator."""
        if obj.rank == 0:
            return mark_safe('<span style="color: #999;">0</span>')
        color = "#10B981" if obj.rank > 0 else "#EF4444"
        return mark_safe(f'<span style="color: {color}; font-weight: 600;">{obj.rank}</span>')

    @admin.display(description="Usage", ordering="usage_count")
    def usage_count_display(self, obj):
        """Display usage count with visual weight."""
        if obj.usage_count == 0:
            return mark_safe('<span style="color: #999;">0</span>')
        # Visual weight based on usage
        if obj.usage_count > 50:
            style = "color: #10B981; font-weight: 700; font-size: 14px;"
        elif obj.usage_count > 20:
            style = "color: #3B82F6; font-weight: 600;"
        elif obj.usage_count > 5:
            style = "color: #6B7280; font-weight: 500;"
        else:
            style = "color: #9CA3AF;"

        return mark_safe(f'<span style="{style}">{obj.usage_count}</span>')

    @admin.display(description="Posts", ordering="_post_count")
    def post_count(self, obj):
        """Display post count with link to filtered posts."""
        count = getattr(obj, "_post_count", 0)
        if count == 0:
            return mark_safe('<span style="color: #999;">0</span>')
        return mark_safe(
            f'<a href="/admin/engine/post/?tags__id__exact={obj.pk}" '
            f'style="color: #3B82F6; font-weight: 500;">{count}</a>'
        )

    @admin.display(description="Aliases", ordering="_alias_count")
    def alias_count_display(self, obj):
        """Display alias count."""
        count = getattr(obj, "_alias_count", 0)
        if count == 0:
            return mark_safe('<span style="color: #999;">0</span>')
        # Show alias names as tooltip
        aliases = obj.aliases.all()
        alias_list = ", ".join([a.alias for a in aliases[:5]])
        if count > 5:
            alias_list += f" (+{count - 5} more)"
        return mark_safe(
            f'<span title="{alias_list}" style="color: #8B5CF6; font-weight: 500; cursor: help;">{count}</span>'
        )

    @admin.display(description="Children", ordering="_children_count")
    def children_count_display(self, obj):
        """Display children count."""
        count = getattr(obj, "_children_count", 0)
        if count == 0:
            return mark_safe('<span style="color: #999;">0</span>')
        return mark_safe(f'<span style="color: #F59E0B; font-weight: 500;">{count}</span>')

    # Bulk actions
    @admin.action(description="Activate selected tags")
    def activate_tags(self, request, queryset):
        """Bulk activate tags."""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"{updated} tag(s) activated successfully.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Deactivate selected tags")
    def deactivate_tags(self, request, queryset):
        """Bulk deactivate tags."""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"{updated} tag(s) deactivated successfully.",
            level=messages.WARNING,
        )

    @admin.action(description="Update usage counts")
    def update_usage_counts(self, request, queryset):
        """Recalculate usage counts for selected tags."""
        count = 0
        for tag in queryset:
            tag.update_usage_count()
            count += 1
        self.message_user(
            request,
            f"Updated usage counts for {count} tag(s).",
            level=messages.SUCCESS,
        )

    @admin.action(description="Export selected tags to CSV")
    def export_tags_csv(self, request, queryset):
        """Export selected tags to CSV file."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="tags_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Name",
                "Namespace",
                "Parent",
                "Description",
                "Color",
                "Icon",
                "Active",
                "Rank",
                "Usage Count",
                "Slug",
                "Created",
            ]
        )

        for tag in queryset:
            writer.writerow(
                [
                    tag.name,
                    tag.namespace or "",
                    tag.parent.name if tag.parent else "",
                    tag.description,
                    tag.color,
                    tag.icon,
                    tag.is_active,
                    tag.rank,
                    tag.usage_count,
                    tag.slug,
                    tag.created_at.strftime("%Y-%m-%d %H:%M"),
                ]
            )

        self.message_user(
            request,
            f"Exported {queryset.count()} tag(s) to CSV.",
            level=messages.SUCCESS,
        )
        return response


# --------------------------
# Tag Alias Admin
# --------------------------
@admin.register(TagAlias)
class TagAliasAdmin(admin.ModelAdmin):
    list_display = (
        "alias",
        "tag_display",
        "slug",
        "created_at",
    )
    list_filter = ("tag__namespace", "created_at")
    search_fields = ("alias", "tag__name", "slug")
    ordering = ("alias",)
    prepopulated_fields = {"slug": ("alias",)}
    list_per_page = 50
    autocomplete_fields = ("tag",)

    @admin.display(description="Canonical Tag", ordering="tag__name")
    def tag_display(self, obj):
        """Display the canonical tag with link and color."""
        return mark_safe(
            f'<a href="/admin/engine/tag/{obj.tag.pk}/change/" '
            f'style="display: inline-block; padding: 4px 10px; border-radius: 12px; '
            f'background-color: {obj.tag.color}; color: white; font-weight: 500; font-size: 13px; '
            f'text-decoration: none;">{obj.tag.name}</a>'
        )


# --------------------------
# Category Admin
# --------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "post_count", "created_at", "updated_at")
    list_filter = ("parent",)
    search_fields = ("name", "description")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("parent",)
    list_select_related = ("parent",)
    list_per_page = 50

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (("name", "slug"), "description", "parent"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Posts", ordering="posts__count")
    def post_count(self, obj):
        count = obj.posts.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<a href="/admin/engine/post/?categories__id__exact={}" style="font-weight: 500;">{}</a>',
            obj.pk,
            count,
        )


# --------------------------
# Series Admin
# --------------------------
@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "post_count", "created_at", "updated_at")
    search_fields = ("title", "description")
    ordering = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    list_per_page = 50

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (("title", "slug"), "description"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Posts", ordering="posts__count")
    def post_count(self, obj):
        count = obj.posts.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<a href="/admin/engine/post/?series__id__exact={}" style="font-weight: 500;">{}</a>',
            obj.pk,
            count,
        )

    class Meta:
        verbose_name_plural = "series"
