"""
Admin classes for Post model and related inlines.

This module contains the admin configuration for posts, including
internal links (backlinks) and post-asset relationships.
"""

import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.safestring import mark_safe



from engine.models import InternalLink, Post, PostAsset

from .mixins import SoftDeleteAdminMixin


class PostAssetInline(admin.StackedInline):
    model = PostAsset
    extra = 1
    min_num = 0
    max_num = 50

    autocomplete_fields = ["asset"]
    ordering = ["order"]

    # Verbose names for better UX
    verbose_name = "Asset"
    verbose_name_plural = "Post Assets"

    fieldsets = [
        (
            None,
            {
                "fields": (
                    ("asset_preview", "asset"),
                    ("alias", "order", "markdown_ref_display"),
                ),
                "classes": [],
            },
        ),
        (
            "Custom Overrides (Optional)",
            {
                "fields": (
                    ("custom_alt_text",),
                    ("custom_caption",),
                ),
                "classes": ["collapse"],
                "description": "Override default asset metadata for this post only",
            },
        ),
    ]

    readonly_fields = ["asset_preview", "markdown_ref_display"]

    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to improve UX."""
        formset = super().get_formset(request, obj, **kwargs)

        # Make alias not required
        if "alias" in formset.form.base_fields:
            formset.form.base_fields["alias"].required = False
            formset.form.base_fields[
                "alias"
            ].help_text = 'Optional: Short name for this post (e.g., "fig1")'
            formset.form.base_fields["alias"].widget.attrs.update(
                {"placeholder": "Leave blank to use global key"}
            )

        # Improve order field
        if "order" in formset.form.base_fields:
            formset.form.base_fields[
                "order"
            ].help_text = "Display order (lower numbers first)"

        # Improve custom fields help text
        if "custom_caption" in formset.form.base_fields:
            formset.form.base_fields[
                "custom_caption"
            ].help_text = "Override default caption for this post only"
            formset.form.base_fields["custom_caption"].widget.attrs.update(
                {"rows": 2, "placeholder": "Leave blank to use asset's default caption"}
            )

        if "custom_alt_text" in formset.form.base_fields:
            formset.form.base_fields[
                "custom_alt_text"
            ].help_text = "Override default alt text for this post only"
            formset.form.base_fields["custom_alt_text"].widget.attrs.update(
                {"placeholder": "Leave blank to use asset's default alt text"}
            )

        return formset

    @admin.display(description="Preview")
    def asset_preview(self, obj):
        """Show enhanced preview in inline."""
        if not obj.asset or not obj.asset.file:
            return format_html(
                '<div style="width: 120px; height: 90px; display: flex; flex-direction: column; align-items: center; justify-content: center; '
                'background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 6px; color: #6c757d;">'
                '<span style="font-size: 32px; margin-bottom: 4px;">📎</span>'
                '<span style="font-size: 11px; opacity: 0.7;">No asset</span>'
                "</div>"
            )

        if obj.asset.asset_type == "image":
            return format_html(
                '<div style="text-align: center;">'
                '<img src="{}" style="max-width: 120px; max-height: 90px; border-radius: 6px; '
                'box-shadow: 0 2px 4px rgba(0,0,0,0.15); border: 1px solid #e9ecef; display: block; margin-bottom: 4px;" />'
                '<div style="font-size: 10px; color: #6c757d;">{} × {}</div>'
                "</div>",
                obj.asset.file.url,
                obj.asset.width or "?",
                obj.asset.height or "?",
            )

        icons_info = {
            "video": ("🎬", "Video", "#dc3545"),
            "audio": ("🎵", "Audio", "#198754"),
            "document": ("📄", "Document", "#0dcaf0"),
            "archive": ("📦", "Archive", "#6610f2"),
            "other": ("📎", "File", "#6c757d"),
        }
        icon, label, color = icons_info.get(
            obj.asset.asset_type, ("📎", "File", "#6c757d")
        )

        return format_html(
            '<div style="width: 120px; height: 90px; display: flex; flex-direction: column; align-items: center; justify-content: center; '
            'background: {}; border-radius: 6px; border: 1px solid {}; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">'
            '<span style="font-size: 40px; opacity: 0.9; margin-bottom: 4px;">{}</span>'
            '<span style="font-size: 11px; color: {}; font-weight: 500;">{}</span>'
            "</div>",
            f"{color}15",
            color,
            icon,
            color,
            label,
        )

    @admin.display(description="Reference")
    def markdown_ref_display(self, obj):
        """Show the markdown reference with copy button."""
        # Generate reference - this displays correctly for saved objects
        if obj.pk and obj.asset:
            if obj.alias:
                ref = f"@{obj.alias}"
            else:
                ref = f"@asset:{obj.asset.key}"
        else:
            ref = "-"

        # Simple display with copy button
        return format_html(
            '<div style="display: flex; align-items: center; gap: 8px;">'
            '<code style="background: #f0f0f0; padding: 4px 8px; border-radius: 3px; font-family: monospace;">{}</code>'
            "<button type='button' "
            "style='padding: 4px 12px; cursor: pointer;' "
            'onclick="'
            "const code = this.previousElementSibling.textContent; "
            "if (code !== '-') {{ "
            "navigator.clipboard.writeText(code).then(() => {{ "
            "const orig = this.textContent; this.textContent = '✓ Copied'; "
            "setTimeout(() => {{ this.textContent = orig; }}, 2000); "
            "}}); "
            "}} else {{ "
            "alert('Please select an asset and save first'); "
            "}} "
            "event.preventDefault();"
            '">Copy</button>'
            "</div>",
            ref,
        )


class IncomingLinksInline(admin.TabularInline):
    """Inline to show backlinks (incoming links) in Post admin."""

    model = InternalLink
    fk_name = "target_post"
    extra = 0
    max_num = 50
    can_delete = False
    verbose_name = "Backlink"
    verbose_name_plural = "Backlinks (Posts Linking to This Post)"

    fields = ("source_post_link", "link_count", "created_at")
    readonly_fields = ("source_post_link", "link_count", "created_at")

    def has_add_permission(self, request, obj=None):
        """Backlinks are auto-generated, not manually added."""
        return False

    @admin.display(description="Source Post")
    def source_post_link(self, obj):
        """Display source post with link to admin."""
        if not obj.pk:
            return "—"
        return format_html(
            '<a href="/admin/engine/post/{}/change/" target="_blank">{}</a>',
            obj.source_post.pk,
            obj.source_post.title,
        )


# --------------------------
# Post admin
# --------------------------
@admin.register(Post)
class PostAdmin(admin.ModelAdmin, SoftDeleteAdminMixin):
    inlines = [PostAssetInline, IncomingLinksInline]
    save_on_top = True
    date_hierarchy = "published_at"

    list_display = (
        "post_title_with_status",
        "author",
        "status_badge",
        "completion_status_badge",
        "visibility_badge",
        "featured_pinned_indicators",
        "show_toc",
        "published_at",
        "stats_compact",
    )

    list_filter = (
        "status",
        "completion_status",
        "visibility",
        "is_featured",
        "is_pinned",
        "show_toc",
        "is_deleted",
        "published_at",
        "created_at",
        "updated_at",
        "categories",
        "tags",
        "series",
        "author",
    )

    search_fields = ("title", "subtitle", "description", "content_markdown", "slug")
    ordering = ("-is_pinned", "pin_order", "-published_at", "-created_at")

    autocomplete_fields = (
        "author",
        "co_authors",
        "series",
        "categories",
        "tags",
        "related_posts",
        "published_by",
        "last_edited_by",
    )

    filter_horizontal = ("co_authors", "categories", "tags", "related_posts")

    readonly_fields = (
        "word_count",
        "reading_time_minutes",
        "table_of_contents",
        "asset_markdown_reference_helper",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    actions = (
        "publish_selected",
        "unpublish_selected",
        "feature_selected",
        "unfeature_selected",
        "rebuild_backlinks_for_selected",
        "soft_delete_selected",
        "restore_selected",
        "export_posts_csv",
    )

    # Slug from title is handy for editors
    prepopulated_fields = {"slug": ("title",)}

    # Show facets for filters
    show_facets = admin.ShowFacets.ALWAYS

    # Optional: nicer widgets for large text fields
    formfield_overrides = {
        admin.widgets.AdminTextareaWidget: {"widget": admin.widgets.AdminTextareaWidget},
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        from django.contrib.admin.widgets import AdminTextareaWidget

        # Make text fields full-width with better editing experience
        if db_field.name == "content_markdown":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 30,
                    "cols": 120,
                    "style": "width: 100%; font-family: monospace; font-size: 16px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        elif db_field.name == "description":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 4,
                    "cols": 120,
                    "style": "width: 100%; font-size: 14px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        elif db_field.name == "abstract":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 8,
                    "cols": 120,
                    "style": "width: 100%; font-family: monospace; font-size: 14px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    ("title", "slug"),
                    ("subtitle", "language"),
                    ("author", "co_authors"),
                ),
                "classes": [],
                "description": "Core post identity and authorship",
            },
        ),
        (
            "Publishing & Status",
            {
                "fields": (
                    ("status", "completion_status"),
                    ("visibility",),
                    ("published_at", "expire_at"),
                    ("is_featured", "is_pinned", "pin_order"),
                    ("published_by", "last_edited_by", "version"),
                ),
                "classes": [],
                "description": "Control post status, visibility, and publication schedule",
            },
        ),
        (
            "Organization & Taxonomy",
            {
                "fields": (
                    ("series",),
                    ("categories", "tags"),
                    ("related_posts", "certainty", "importance"),
                    (
                        "show_toc",
                        "first_line_caps",
                    ),
                ),
                "classes": ["collapse"],
                "description": "Categorize and relate your content",
            },
        ),
        (
            "Content",
            {
                "fields": (
                    ("description",),
                    ("abstract",),
                    ("content_markdown",),
                    ("asset_markdown_reference_helper",),
                ),
                "description": "Write your post content in Markdown. The renderer automatically processes this when displayed in templates.",
            },
        ),
        (
            "Engagement & Analytics",
            {
                "fields": (
                    ("allow_comments", "comment_count"),
                    ("view_count", "like_count", "rating"),
                    ("reading_time_minutes", "word_count"),
                ),
                "classes": ["collapse"],
                "description": "User engagement metrics and reading statistics",
            },
        ),
        (
            "Advanced",
            {
                "fields": (
                    ("table_of_contents",),
                    ("content_html_cached",),
                    ("extras",),
                ),
                "classes": ["collapse"],
                "description": "Advanced settings and metadata",
            },
        ),
        (
            "System Information",
            {
                "fields": (
                    ("created_at", "updated_at"),
                    ("is_deleted", "deleted_at"),
                ),
                "classes": ["collapse"],
                "description": "System-managed timestamps and soft-delete status",
            },
        ),
    )

    @admin.display(description="Post", ordering="title")
    def post_title_with_status(self, obj):
        """Display post title with visual indicators."""
        # Status emoji
        status_icons = {
            "draft": "📝",
            "scheduled": "⏰",
            "published": "✅",
            "archived": "📦",
        }
        icon = status_icons.get(obj.status, "📄")

        # Title with bold if featured
        title_style = "font-weight: 600;" if obj.is_featured else ""

        return format_html(
            '<div style="display: flex; align-items: center; gap: 8px;">'
            '<span style="font-size: 18px;">{}</span>'
            '<span style="{}">{}</span>'
            "</div>",
            icon,
            title_style,
            obj.title,
        )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            "draft": "#fff3cd",
            "scheduled": "#cfe2ff",
            "published": "#d4edda",
            "archived": "#e2e3e5",
        }
        text_colors = {
            "draft": "#856404",
            "scheduled": "#084298",
            "published": "#155724",
            "archived": "#383d41",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            colors.get(obj.status, "#e2e3e5"),
            text_colors.get(obj.status, "#383d41"),
            obj.get_status_display(),
        )

    @admin.display(description="Completion", ordering="completion_status")
    def completion_status_badge(self, obj):
        """Display completion status with color."""
        colors = {
            "finished": "#d4edda",
            "abandoned": "#f8d7da",
            "notes": "#d1ecf1",
            "draft": "#fff3cd",
            "in_progress": "#cfe2ff",
        }
        text_colors = {
            "finished": "#155724",
            "abandoned": "#721c24",
            "notes": "#0c5460",
            "draft": "#856404",
            "in_progress": "#084298",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            colors.get(obj.completion_status, "#e2e3e5"),
            text_colors.get(obj.completion_status, "#383d41"),
            obj.get_completion_status_display(),
        )

    @admin.display(description="Visibility", ordering="visibility")
    def visibility_badge(self, obj):
        """Display visibility with color."""
        colors = {
            "public": "#d4edda",
            "unlisted": "#fff3cd",
            "private": "#f8d7da",
        }
        text_colors = {
            "public": "#155724",
            "unlisted": "#856404",
            "private": "#721c24",
        }
        icons = {
            "public": "🌐",
            "unlisted": "🔗",
            "private": "🔒",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{} {}</span>',
            colors.get(obj.visibility, "#e2e3e5"),
            text_colors.get(obj.visibility, "#383d41"),
            icons.get(obj.visibility, ""),
            obj.get_visibility_display(),
        )

    @admin.display(description="Features")
    def featured_pinned_indicators(self, obj):
        """Show featured/pinned indicators."""
        badges = []
        if obj.is_featured:
            badges.append(
                '<span style="background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 3px; font-size: 10px;">⭐ FEATURED</span>'
            )
        if obj.is_pinned:
            badges.append(
                f'<span style="background: #e0e7ff; color: #3730a3; padding: 2px 6px; border-radius: 3px; font-size: 10px;">📌 PIN {obj.pin_order}</span>'
            )
        if not badges:
            return format_html('<span style="color: #999;">—</span>')
        return format_html(" ".join(badges))

    @admin.display(description="Stats")
    def stats_compact(self, obj):
        """Display compact statistics."""
        return format_html(
            '<div style="font-size: 11px; color: #6c757d;">'
            "<div>👁️ {} | 💬 {} | ❤️ {}</div>"
            "<div>📖 {}min | {} words</div>"
            "</div>",
            obj.view_count,
            obj.comment_count,
            obj.like_count,
            obj.reading_time_minutes,
            obj.word_count,
        )

    @admin.display(description="Asset Markdown References")
    def asset_markdown_reference_helper(self, obj=None):
        """Display assets attached to this post with their markdown references for quick copying."""
        # If no post object (add page), show help message
        if not obj or not obj.pk:
            return mark_safe(
                '<div style="padding: 12px; background: #e7f3ff; border: 1px solid #0dcaf0; border-radius: 4px; color: #004085;">'
                'ℹ️ Asset references will appear here after you add assets to this post in the "Post Assets" section below.'
                "</div>"
            )

        # Get assets attached to this post via PostAsset relationship
        post_assets = obj.post_assets.select_related("asset").order_by("order")

        if not post_assets.exists():
            return mark_safe(
                '<div style="padding: 12px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
                '⚠️ No assets attached to this post yet. Add assets in the "Post Assets" section below, then save to see their markdown references here.'
                "</div>"
            )

        # Build HTML parts as a list to avoid string concatenation issues
        parts = []
        parts.append(
            '<div style="max-height: 400px; overflow-y: auto; border: 1px solid #e0e0e0; border-radius: 4px; padding: 12px; background: #f9f9f9;">'
        )
        parts.append(
            f'<div style="margin-bottom: 8px; font-weight: 600; color: #333;">📎 Assets in this Post ({post_assets.count()}) — Click to copy:</div>'
        )
        parts.append(
            '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px;">'
        )

        for post_asset in post_assets:
            asset = post_asset.asset

            # Determine the reference to use (alias or asset key)
            if post_asset.alias:
                ref = "@" + post_asset.alias
                ref_type = "Alias"
            else:
                ref = "@asset:" + asset.key
                ref_type = "Global"

            # Get asset type icon
            icons = {
                "image": "🖼️",
                "video": "🎬",
                "audio": "🎵",
                "document": "📄",
                "archive": "📦",
                "other": "📎",
            }
            icon = icons.get(asset.asset_type, "📎")

            # Truncate title
            display_title = asset.title[:40] if len(asset.title) > 40 else asset.title

            # Add order indicator
            order_badge = (
                f'<span style="background: #e9ecef; padding: 2px 6px; border-radius: 2px; font-size: 9px; font-weight: 600; margin-right: 4px;">#{post_asset.order}</span>'
                if post_asset.order
                else ""
            )

            parts.append(
                f"""
            <div class="asset-ref-card" data-ref="{ref}" style="background: white; border: 1px solid #ddd; border-radius: 3px; padding: 8px; cursor: pointer;">
                <div style="font-size: 11px; color: #666; margin-bottom: 3px;">{order_badge}{icon} {asset.asset_type.title()} <span style="color: #999;">• {ref_type}</span></div>
                <div style="font-weight: 500; font-size: 13px; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{asset.title}">{display_title}</div>
                <code style="font-size: 10px; background: #f5f5f5; padding: 2px 4px; border-radius: 2px; display: block; font-family: monospace;">{ref}</code>
            </div>
            """
            )

        parts.append("</div></div>")
        parts.append(
            '<div style="margin-top: 8px; padding: 8px; background: #e7f3ff; border-radius: 3px; font-size: 11px; color: #004085;">💡 <strong>Tip:</strong> Click any asset card above to copy its markdown reference.</div>'
        )

        # Add JavaScript for click handling
        parts.append(
            """
        <script>
        (function() {
            setTimeout(function() {
                document.querySelectorAll('.asset-ref-card').forEach(function(card) {
                    if (card.hasAttribute('data-listener')) return;
                    card.setAttribute('data-listener', 'true');

                    card.addEventListener('click', function() {
                        var ref = this.getAttribute('data-ref');
                        navigator.clipboard.writeText(ref).then(function() {
                            card.style.background = '#d4edda';
                            card.style.borderColor = '#28a745';
                            setTimeout(function() {
                                card.style.background = 'white';
                                card.style.borderColor = '#ddd';
                            }, 2000);
                        });
                    });

                    card.addEventListener('mouseover', function() {
                        if (this.style.background !== 'rgb(212, 237, 218)') {
                            this.style.background = '#f8f9fa';
                            this.style.borderColor = '#999';
                        }
                    });

                    card.addEventListener('mouseout', function() {
                        if (this.style.background !== 'rgb(212, 237, 218)') {
                            this.style.background = 'white';
                            this.style.borderColor = '#ddd';
                        }
                    });
                });
            }, 500);
        })();
        </script>
        """
        )

        return mark_safe("".join(parts))

    @admin.action(description="Publish selected posts")
    def publish_selected(self, request, queryset):
        """Publish selected posts."""
        from django.utils import timezone

        count = 0
        for post in queryset:
            post.status = "published"
            if not post.published_at:
                post.published_at = timezone.now()
            post.save()
            count += 1
        self.message_user(request, f"Published {count} post(s).")

    @admin.action(description="Unpublish selected posts")
    def unpublish_selected(self, request, queryset):
        """Unpublish selected posts."""
        count = queryset.update(status="draft")
        self.message_user(request, f"Unpublished {count} post(s).")

    @admin.action(description="Feature selected posts")
    def feature_selected(self, request, queryset):
        """Mark selected posts as featured."""
        count = queryset.update(is_featured=True)
        self.message_user(request, f"Featured {count} post(s).")

    @admin.action(description="Unfeature selected posts")
    def unfeature_selected(self, request, queryset):
        """Remove featured status from selected posts."""
        count = queryset.update(is_featured=False)
        self.message_user(request, f"Unfeatured {count} post(s).")

    @admin.action(description="Rebuild backlinks for selected posts")
    def rebuild_backlinks_for_selected(self, request, queryset):
        """Rebuild internal links for selected posts by parsing their content."""
        from engine.links.extractor import update_post_links

        total_stats = {
            "posts_processed": 0,
            "links_created": 0,
            "links_updated": 0,
            "links_deleted": 0,
            "links_failed": 0,
        }

        for post in queryset:
            try:
                stats = update_post_links(post)
                total_stats["posts_processed"] += 1
                total_stats["links_created"] += stats["links_created"]
                total_stats["links_updated"] += stats["links_updated"]
                total_stats["links_deleted"] += stats["links_deleted"]
                total_stats["links_failed"] += stats["links_failed"]
            except Exception as e:
                self.message_user(
                    request,
                    f"Error processing '{post.title}': {str(e)}",
                    level=messages.ERROR,
                )

        # Show summary
        self.message_user(
            request,
            f"Processed {total_stats['posts_processed']} post(s): "
            f"{total_stats['links_created']} links created, "
            f"{total_stats['links_updated']} updated, "
            f"{total_stats['links_deleted']} deleted.",
            level=messages.SUCCESS,
        )

        if total_stats["links_failed"] > 0:
            self.message_user(
                request,
                f"Warning: {total_stats['links_failed']} link(s) failed to resolve.",
                level=messages.WARNING,
            )

    @admin.action(description="Export selected posts as CSV")
    def export_posts_csv(self, request, queryset):
        """Export posts as CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="posts_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Title",
                "Slug",
                "Author",
                "Status",
                "Visibility",
                "Published",
                "Word Count",
                "Reading Time",
                "Views",
                "Comments",
                "Likes",
                "Featured",
                "Pinned",
                "Created",
                "Updated",
            ]
        )

        for post in queryset:
            writer.writerow(
                [
                    post.title,
                    post.slug,
                    post.author.username,
                    post.get_status_display(),
                    post.get_visibility_display(),
                    (
                        post.published_at.strftime("%Y-%m-%d %H:%M")
                        if post.published_at
                        else ""
                    ),
                    post.word_count,
                    post.reading_time_minutes,
                    post.view_count,
                    post.comment_count,
                    post.like_count,
                    "Yes" if post.is_featured else "No",
                    "Yes" if post.is_pinned else "No",
                    post.created_at.strftime("%Y-%m-%d %H:%M"),
                    post.updated_at.strftime("%Y-%m-%d %H:%M"),
                ]
            )

        return response


# --------------------------
# Internal Links (Backlinks)
# --------------------------
@admin.register(InternalLink)
class InternalLinkAdmin(admin.ModelAdmin):
    """Admin for internal links between posts."""

    list_display = (
        "link_display",
        "link_text_preview",
        "link_type_badge",
        "created_at",
    )
    list_filter = (
        "created_at",
        "is_deleted",
    )
    search_fields = (
        "source_post__title",
        "source_post__slug",
        "target_post__title",
        "target_post__slug",
        "link_text",
    )
    list_select_related = ("source_post", "target_post")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 100

    fieldsets = (
        (
            "Link Relationship",
            {
                "fields": (
                    ("source_post", "target_post"),
                    "link_count",
                ),
                "classes": [],
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
        (
            "System",
            {
                "fields": (("is_deleted", "deleted_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    @admin.display(description="Link", ordering="source_post__title")
    def link_display(self, obj):
        """Display the link relationship."""
        return format_html(
            '<div style="font-size: 12px;">'
            '<a href="/admin/engine/post/{}/change/" style="color: #0066cc;">{}</a>'
            '<span style="margin: 0 8px; color: #999;">→</span>'
            '<a href="/admin/engine/post/{}/change/" style="color: #0066cc;">{}</a>'
            "</div>",
            obj.source_post.pk,
            obj.source_post.title[:40],
            obj.target_post.pk,
            obj.target_post.title[:40],
        )

    @admin.display(description="Link Text")
    def link_text_preview(self, obj):
        """Display truncated link text."""
        if not obj.link_text:
            return format_html('<span style="color: #999;">—</span>')
        text = obj.link_text[:60] + "..." if len(obj.link_text) > 60 else obj.link_text
        return format_html(
            '<span style="font-size: 11px; color: #666;">"<em>{}</em>"</span>', text
        )

    @admin.display(description="Type")
    def link_type_badge(self, obj):
        """Display link direction."""
        return format_html(
            '<span style="background: #e7f3ff; color: #004085; padding: 4px 8px; '
            'border-radius: 4px; font-size: 10px; font-weight: 500;">Internal Link</span>'
        )
