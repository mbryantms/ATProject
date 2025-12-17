"""
Page model for static/editable content pages.

Used for pages like the homepage intro that need editable content
stored in the database. Can also store configuration like featured tags.
"""

from django.db import models

from engine.markdown.renderer import render_markdown

from .base import TimeStampedModel


class Page(TimeStampedModel):
    """
    A page model for storing editable content and page-specific configuration.

    Content is written in Markdown and rendered to HTML on save.
    Can also store related tags for featured sections (e.g., homepage).
    """

    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-friendly identifier for this page (e.g., 'home-intro')",
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional title for the page",
    )
    content = models.TextField(
        blank=True,
        help_text="Markdown content for this page",
    )
    content_html = models.TextField(
        blank=True,
        editable=False,
        help_text="Rendered HTML (auto-generated from content)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this page content is active",
    )
    featured_tags = models.ManyToManyField(
        "Tag",
        through="PageFeaturedTag",
        blank=True,
        help_text="Tags to feature on this page (with custom titles and ordering)",
    )

    class Meta:
        ordering = ["slug"]
        verbose_name = "Page"
        verbose_name_plural = "Pages"

    def __str__(self):
        return self.title or self.slug

    def save(self, *args, **kwargs):
        if self.content:
            self.content_html = render_markdown(self.content)
        else:
            self.content_html = ""
        super().save(*args, **kwargs)

    @classmethod
    def get_content(cls, slug, default=""):
        """
        Get the rendered HTML content for a page by slug.

        Returns the default if the page doesn't exist or is inactive.
        """
        try:
            page = cls.objects.get(slug=slug, is_active=True)
            return page.content_html
        except cls.DoesNotExist:
            return default

    def get_featured_tags_config(self):
        """
        Get featured tags configuration for this page.

        Returns a list of dicts with 'tag' and 'display_title' keys,
        ordered by the configured order.
        """
        return [
            {
                "tag": pft.tag,
                "display_title": pft.display_title or pft.tag.name,
            }
            for pft in self.pagefeaturedtag_set.select_related("tag").order_by("order")
        ]


class PageFeaturedTag(models.Model):
    """
    Through model for Page featured tags with ordering and custom display titles.
    """

    page = models.ForeignKey(Page, on_delete=models.CASCADE)
    tag = models.ForeignKey("Tag", on_delete=models.CASCADE)
    display_title = models.CharField(
        max_length=100,
        blank=True,
        help_text="Custom title for this section (defaults to tag name)",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)",
    )

    class Meta:
        ordering = ["order"]
        unique_together = [["page", "tag"]]
        verbose_name = "Featured Tag"
        verbose_name_plural = "Featured Tags"

    def __str__(self):
        return f"{self.page.slug}: {self.tag.name}"
