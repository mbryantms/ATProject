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

from engine.models import Category, Series, Tag, TagAlias

from .display import admin_change_link, admin_changelist_link, muted
from .widgets import ColorInput, GlyphPickerInput


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
    class Media:
        css = {"all": ("css/admin-common.css",)}

    list_display = (
        "colored_name_display",
        "namespace_display",
        "parent_display",
        "is_active_display",
        "rank_display",
        "usage_count_display",
        "post_count",
        "alias_count_display",
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

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Pickers for the visual-styling fields: a native color dialog with
        # preset swatches, and a glyph palette for the icon. Both keep the
        # underlying CharField free-typed.
        if db_field.name == "color":
            kwargs["widget"] = ColorInput()
        elif db_field.name == "icon":
            kwargs["widget"] = GlyphPickerInput()
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs.select_related("parent")
            .prefetch_related("aliases")
            .annotate(
                _post_count=models.Count("posts", distinct=True),
                _alias_count=models.Count("aliases", distinct=True),
            )
        )

    # Custom display methods. Colors that are semantic use the shared theme-
    # aware mk-* classes (admin-common.css); the tag's own configured color is
    # the one intentional exception (it is the tag's identity) and is escaped
    # via format_html.
    @admin.display(description="Tag", ordering="name")
    def colored_name_display(self, obj):
        """Display tag name as a badge in the tag's own configured color."""
        icon = format_html("{} ", obj.icon) if obj.icon else ""
        return format_html(
            '{}<span style="display:inline-block;padding:3px 9px;border-radius:10px;'
            'background-color:{};color:#fff;font-weight:500;font-size:12px;">{}</span>',
            icon,
            obj.color,
            obj.name,
        )

    @admin.display(description="Namespace", ordering="namespace")
    def namespace_display(self, obj):
        if not obj.namespace:
            return muted()
        return format_html('<span class="mk-pill mk-pill--sm">{}</span>', obj.namespace)

    @admin.display(description="Parent", ordering="parent__name")
    def parent_display(self, obj):
        if not obj.parent:
            return muted("Root")
        return admin_change_link(obj.parent, obj.parent.name)

    @admin.display(description="Active", ordering="is_active", boolean=True)
    def is_active_display(self, obj):
        return obj.is_active

    @admin.display(description="Rank", ordering="rank")
    def rank_display(self, obj):
        if obj.rank == 0:
            return muted("0")
        return format_html("<span class='mk-bold'>{}</span>", obj.rank)

    @admin.display(description="Usage", ordering="usage_count")
    def usage_count_display(self, obj):
        if obj.usage_count == 0:
            return muted("0")
        return format_html("<span class='mk-bold'>{}</span>", obj.usage_count)

    @admin.display(description="Posts", ordering="_post_count")
    def post_count(self, obj):
        count = getattr(obj, "_post_count", 0)
        if count == 0:
            return muted("0")
        from engine.models import Post

        return admin_changelist_link(Post, count, tags__id__exact=obj.pk)

    @admin.display(description="Aliases", ordering="_alias_count")
    def alias_count_display(self, obj):
        count = getattr(obj, "_alias_count", 0)
        if count == 0:
            return muted("0")
        # aliases are prefetched; slice in Python to build the tooltip
        names = [a.alias for a in list(obj.aliases.all())[:5]]
        tooltip = ", ".join(names)
        if count > 5:
            tooltip += f" (+{count - 5} more)"
        return format_html('<span title="{}">{}</span>', tooltip, count)

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
        """Recalculate usage counts for selected tags in bulk."""
        from django.db.models import Count

        tags = list(queryset.annotate(_count=Count("posts")).only("id", "usage_count"))
        to_update = []
        for tag in tags:
            if tag.usage_count != tag._count:
                tag.usage_count = tag._count
                to_update.append(tag)
        if to_update:
            Tag.objects.bulk_update(to_update, ["usage_count"])
        self.message_user(
            request,
            f"Updated usage counts for {len(tags)} tag(s) ({len(to_update)} changed).",
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

    list_select_related = ("tag",)

    @admin.display(description="Canonical Tag", ordering="tag__name")
    def tag_display(self, obj):
        """Display the canonical tag as a link in the tag's own color."""
        return admin_change_link(
            obj.tag,
            format_html(
                '<span style="display:inline-block;padding:3px 9px;border-radius:10px;'
                'background-color:{};color:#fff;font-weight:500;font-size:12px;">{}</span>',
                obj.tag.color,
                obj.tag.name,
            ),
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

    def get_queryset(self, request):
        # Annotate the post count once instead of a per-row COUNT query in
        # post_count() (N+1 across the 50-row changelist).
        return (
            super()
            .get_queryset(request)
            .annotate(_post_count=models.Count("posts", distinct=True))
        )

    @admin.display(description="Posts", ordering="_post_count")
    def post_count(self, obj):
        count = getattr(obj, "_post_count", 0)
        if count == 0:
            return muted("0")
        from engine.models import Post

        return admin_changelist_link(Post, count, categories__id__exact=obj.pk)


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

    def get_queryset(self, request):
        # Annotate the post count once instead of a per-row COUNT query in
        # post_count() (N+1 across the 50-row changelist).
        return (
            super()
            .get_queryset(request)
            .annotate(_post_count=models.Count("posts", distinct=True))
        )

    @admin.display(description="Posts", ordering="_post_count")
    def post_count(self, obj):
        count = getattr(obj, "_post_count", 0)
        if count == 0:
            return muted("0")
        from engine.models import Post

        return admin_changelist_link(Post, count, series__id__exact=obj.pk)
