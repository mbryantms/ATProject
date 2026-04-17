"""
Post models for content management.

Includes Post (with queryset/manager), and InternalLink for backlinks tracking.
"""

import copy
import re

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.template.defaultfilters import slugify
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.functional import cached_property

from engine.markdown.extensions.toc_extractor import (
    HeadingNode,
    normalize_toc_structure,
)
from engine.tasks import update_post_derived_content

from .base import (
    SoftDeleteManager,
    SoftDeleteModel,
    SoftDeleteQuerySet,
    TimeStampedModel,
    UniqueSlugMixin,
)


class PostQuerySet(SoftDeleteQuerySet):
    def public(self):
        return self.filter(visibility=Post.Visibility.PUBLIC)

    def unlisted(self):
        return self.filter(visibility=Post.Visibility.UNLISTED)

    def private(self):
        return self.filter(visibility=Post.Visibility.PRIVATE)

    def published(self):
        now = timezone.now()
        return self.filter(
            status=Post.Status.PUBLISHED,
            published_at__isnull=False,
            published_at__lte=now,
        )

    def scheduled(self):
        now = timezone.now()
        return self.filter(
            status=Post.Status.SCHEDULED,
            published_at__isnull=False,
            published_at__gt=now,
        )

    def drafts(self):
        return self.filter(status=Post.Status.DRAFT)

    def featured(self):
        return self.filter(is_featured=True)


class PostManager(SoftDeleteManager):
    """
    Custom manager for Post model that properly exposes PostQuerySet methods.

    Django's automatic manager method proxying from QuerySet doesn't always work
    reliably, especially during app initialization. Explicitly defining these
    methods ensures they're always available on Post.objects.
    """

    def get_queryset(self):
        return PostQuerySet(self.model, using=self._db).alive()

    def public(self):
        return self.get_queryset().public()

    def unlisted(self):
        return self.get_queryset().unlisted()

    def private(self):
        return self.get_queryset().private()

    def published(self):
        return self.get_queryset().published()

    def scheduled(self):
        return self.get_queryset().scheduled()

    def drafts(self):
        return self.get_queryset().drafts()

    def featured(self):
        return self.get_queryset().featured()


class Post(TimeStampedModel, SoftDeleteModel, UniqueSlugMixin):
    """
    Authoring is Markdown only.
    Rendering to HTML happens OUTSIDE the model (service/template filter),
    optionally stored in `content_html_cached` for performance.
    """

    # --- Editorial states/visibility ---
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        UNLISTED = "unlisted", "Unlisted"
        PRIVATE = "private", "Private"

    class CompletionStatus(models.TextChoices):
        FINISHED = "finished", "Finished"
        ABANDONED = "abandoned", "Abandoned"
        NOTES = "notes", "Notes"
        DRAFT = "draft", "Draft"
        IN_PROGRESS = "in_progress", "In Progress"

    VALUE_CHOICES = [(i, str(i)) for i in range(1, 11)]

    # --- Core fields ---
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=240, blank=True)
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        help_text="Auto-generated from title if blank.",
    )

    description = models.TextField(blank=True, help_text="Optional summary/teaser.")
    abstract = models.TextField(
        blank=True,
        help_text="Optional article abstract in markdown (longer-form description, similar to journal article abstract).",
    )

    show_toc = models.BooleanField(
        default=False,
        help_text="Optionally show table of contents.",
        verbose_name="Show Table of Contents",
    )
    first_line_caps = models.BooleanField(
        default=False,
        verbose_name="Intro Paragraph Small Caps",
        help_text="Style the first line of opening paragraph with small caps.",
    )

    # Markdown source of truth
    content_markdown = models.TextField(help_text="Author in markdown only.")

    # Optional cached HTML (filled by your service/signal/Celery task)
    content_html_cached = models.TextField(
        blank=True, help_text="Optional cache of rendered+processed HTML."
    )

    # Derived stats
    word_count = models.PositiveIntegerField(default=0)
    reading_time_minutes = models.PositiveSmallIntegerField(
        default=1, help_text="Approximate reading time."
    )
    language = models.CharField(
        max_length=12, default="en", help_text="IETF tag, e.g., 'en', 'zh-TW'."
    )
    citation_style = models.CharField(
        max_length=100,
        blank=True,
        help_text="CSL citation style override for this post (e.g., 'chicago-author-date'). "
        "Leave blank to use the site-wide default.",
    )

    # --- Publication ---
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    completion_status = models.CharField(
        max_length=20,
        choices=CompletionStatus.choices,
        default=CompletionStatus.DRAFT,
        db_index=True,
        help_text="Editorial completion state shown in page metadata.",
    )
    visibility = models.CharField(
        max_length=12,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
        db_index=True,
    )
    published_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="Go-live time."
    )
    expire_at = models.DateTimeField(
        null=True, blank=True, help_text="Optional unpublish time."
    )

    is_featured = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    pin_order = models.IntegerField(default=0)

    # --- Relationships ---
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="posts"
    )
    co_authors = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="posts_coauthored"
    )
    series = models.ForeignKey(
        "engine.Series",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="posts",
    )
    series_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Manual ordering within a series (lower numbers appear first).",
    )
    categories = models.ManyToManyField(
        "engine.Category", blank=True, related_name="posts"
    )
    tags = models.ManyToManyField("engine.Tag", blank=True, related_name="posts")
    related_posts = models.ManyToManyField(
        "self", blank=True, symmetrical=False, related_name="related_to"
    )

    # --- Media ---
    hero_image_url = models.URLField(
        blank=True, help_text="Featured image URL for social sharing and cards."
    )

    # --- SEO / Social ---
    canonical_url = models.URLField(
        blank=True,
        help_text="Override canonical URL for syndicated/cross-posted content.",
    )
    meta_description = models.CharField(
        max_length=300,
        blank=True,
        help_text="Override meta description (falls back to description field).",
    )
    og_image_url = models.URLField(
        blank=True, help_text="Override Open Graph image URL."
    )
    noindex = models.BooleanField(
        default=False, help_text="Prevent search engines from indexing this post."
    )

    # --- Interactions / Metrics ---
    allow_comments = models.BooleanField(default=True)
    comment_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    like_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    certainty = models.PositiveIntegerField(choices=VALUE_CHOICES, default=1)
    importance = models.PositiveIntegerField(choices=VALUE_CHOICES, default=1)

    # --- Audit / Extensibility ---
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="posts_published",
    )
    last_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="posts_edited",
    )
    version = models.PositiveIntegerField(default=1)
    extras = models.JSONField(blank=True, null=True)
    table_of_contents = models.JSONField(blank=True, null=True)

    # --- Full-Text Search ---
    search_vector = SearchVectorField(
        null=True,
        blank=True,
        help_text="Populated automatically for full-text search. Combines title, subtitle, description, abstract, and content.",
    )

    # Managers
    objects = PostManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-is_pinned", "pin_order", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["visibility", "published_at"]),
            models.Index(fields=["completion_status"]),
            GinIndex(fields=["search_vector"], name="post_search_vector_gin"),
        ]
        constraints = [
            models.CheckConstraint(
                name="published_or_scheduled_requires_published_at",
                condition=(
                    Q(status__in=["draft", "archived"]) | Q(published_at__isnull=False)
                ),
            ),
        ]

    def __str__(self) -> str:
        return self.title

    # ---------------------------
    # Lifecycle (model-only concerns)
    # ---------------------------

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug(slugify(self.title) or "post")

        # --- Check for content changes to trigger async tasks ---
        run_async_tasks = False
        content_changed = False
        is_new = self.pk is None
        if is_new:
            run_async_tasks = True
            content_changed = True
        else:
            try:
                # Fetch the original object from DB
                original = Post.objects.get(pk=self.pk)
                if original.content_markdown != self.content_markdown:
                    run_async_tasks = True
                    content_changed = True
                    self.version = original.version + 1
                    # Clear stale content that will be regenerated
                    self.table_of_contents = []
            except Post.DoesNotExist:
                # This case is unlikely but good to handle
                run_async_tasks = True
                content_changed = True

        # --- Update fast-running derived stats synchronously ---
        self.word_count = self._compute_word_count(self.content_markdown or "")
        self.reading_time_minutes = max(1, round(self.word_count / 225.0 + 0.0001))

        # --- Save the model ---
        super().save(*args, **kwargs)

        # --- Create a revision snapshot when content changes ---
        if content_changed and self.content_markdown:
            PostRevision.objects.get_or_create(
                post=self,
                version=self.version,
                defaults={
                    "content_markdown": self.content_markdown,
                    "created_by": self.last_edited_by,
                },
            )

        # --- Schedule slow tasks after transaction commits ---
        if run_async_tasks:
            transaction.on_commit(lambda: update_post_derived_content.delay(self.pk))

    def clean(self):
        if self.expire_at and self.published_at and self.expire_at <= self.published_at:
            raise ValidationError(
                {"expire_at": "Expiration must be after the publish time."}
            )

    # ---------------------------
    # Helpers
    # ---------------------------

    @property
    def is_published(self) -> bool:
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
            and not self.is_deleted
        )

    # ---------------------------
    # SEO helpers
    # ---------------------------

    def get_meta_description(self) -> str:
        """Return best available meta description: override → description → truncated abstract → title."""
        if self.meta_description:
            return self.meta_description
        if self.description:
            return self.description[:300]
        if self.abstract:
            plain = re.sub(r"[#*_`\[\]()]", "", self.abstract)
            if len(plain) > 300:
                return plain[:300].rsplit(" ", 1)[0] + "…"
            return plain
        # Last resort: compose from title and subtitle
        parts = [self.title]
        if self.subtitle:
            parts.append(self.subtitle)
        return " — ".join(parts)

    def get_og_image_url(self) -> str:
        """Return best available OG image: override → hero → first image asset rendition."""
        if self.og_image_url:
            return self.og_image_url
        if self.hero_image_url:
            return self.hero_image_url
        first_image = (
            self.post_assets.filter(asset__asset_type="image", asset__status="ready")
            .select_related("asset")
            .first()
        )
        if first_image:
            rendition = first_image.asset.renditions.filter(
                width=1200, status="completed"
            ).first()
            if rendition:
                return rendition.url
            return first_image.asset.url
        return ""

    def get_canonical_url(self, site_url: str = "") -> str:
        """Return canonical URL: override or site_url + absolute path."""
        if self.canonical_url:
            return self.canonical_url
        return f"{site_url}{self.get_absolute_url()}"

    def should_noindex(self) -> bool:
        """Return True if the post should not be indexed by search engines."""
        if self.noindex:
            return True
        return self.visibility in (self.Visibility.PRIVATE, self.Visibility.UNLISTED)

    # Browser-only chrome that we strip when serving HTML to feed readers.
    # Section/math copy buttons render as SVG noise in feeds; reference-anchor
    # links duplicate the <ol> marker (browsers hide one via CSS, feed readers
    # show both, producing "1. 1." numbering).
    _FEED_STRIP_SELECTORS = (
        "button.copy-section-link-button",
        "span.block-button-bar",
        "a.reference-anchor",
    )

    def get_feed_html(self) -> str:
        """Return content HTML cleaned for syndication (RSS/Atom)."""
        if not self.content_html_cached:
            return self.description or self.abstract or ""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(self.content_html_cached, "html.parser")
        for selector in self._FEED_STRIP_SELECTORS:
            for el in soup.select(selector):
                el.decompose()
        return str(soup)

    @property
    def completion_status_label(self) -> str:
        """
        Human readable label for the current completion status.

        Falls back to a prettified version of the raw value if someone
        manually stores an unknown status string.
        """
        try:
            return self.CompletionStatus(self.completion_status).label
        except ValueError:
            return self.completion_status.replace("_", " ").strip().title()

    @cached_property
    def toc_tree(self):
        """Normalized hierarchical TOC derived from stored JSON."""
        return normalize_toc_structure(self.table_of_contents or [])

    @cached_property
    def has_footnotes(self) -> bool:
        """Return True when the markdown contains footnote references."""
        text = self.content_markdown or ""
        return bool(re.search(r"\[\^[^\]]+\]", text))

    def get_render_toc(
        self,
        *,
        backlinks_count: int = 0,
        similar_posts_count: int = 0,
        citations_count: int = 0,
    ) -> list[HeadingNode]:
        """
        Produce a TOC tailored for templates, ensuring auxiliary sections appear last.

        Backlinks and similar posts live outside the Markdown body, so we create
        synthetic entries when those sections are rendered. Footnotes entries are
        added when the document contains footnotes but the stored TOC predates the
        extractor update that emits them.
        """
        tree: list[HeadingNode] = copy.deepcopy(self.toc_tree)

        extras: list[HeadingNode] = []

        def contains(nodes: list[HeadingNode], target: str) -> bool:
            for node in nodes:
                if node["id"] == target:
                    return True
                if contains(node.get("children", []), target):
                    return True
            return False

        if citations_count > 0 and not contains(tree, "references"):
            extras.append(
                {
                    "level": 1,
                    "id": "references",
                    "title": "References",
                    "title_html": "References",
                    "children": [],
                }
            )

        if self.has_footnotes and not contains(tree, "footnotes"):
            extras.append(
                {
                    "level": 1,
                    "id": "footnotes",
                    "title": "Footnotes",
                    "title_html": "Footnotes",
                    "children": [],
                }
            )

        if backlinks_count > 0:
            extras.append(
                {
                    "level": 1,
                    "id": "backlinks-section",
                    "title": "Backlinks",
                    "title_html": "Backlinks",
                    "children": [],
                }
            )

        if similar_posts_count > 0:
            extras.append(
                {
                    "level": 1,
                    "id": "similar-posts-section",
                    "title": "Similar Links",
                    "title_html": "Similar Links",
                    "children": [],
                }
            )

        return tree + extras

    def get_absolute_url(self) -> str:
        try:
            return reverse("post-detail", kwargs={"slug": self.slug})
        except NoReverseMatch:
            return f"/posts/{self.slug}/"

    def get_similar_posts(
        self,
        limit: int = 6,
        min_score: float | None = None,
        *,
        include_private: bool = False,
    ):
        """
        Return posts automatically ranked for similarity.

        Manual curation via ``related_posts`` is intentionally avoided here;
        instead we rely on shared taxonomy data and lightweight content
        analysis for ranking. ``include_private`` can be used for staff tools.
        """
        from engine.similarity import MIN_SCORE_DEFAULT, compute_similar_posts

        threshold = MIN_SCORE_DEFAULT if min_score is None else min_score
        return compute_similar_posts(
            self,
            limit=limit,
            min_score=threshold,
            allow_private=include_private,
        )

    @staticmethod
    def _compute_word_count(text: str) -> int:
        if not text:
            return 0
        return len(re.findall(r"\w+", text))


class PostRevision(models.Model):
    """Stores a snapshot of content_markdown each time it changes."""

    post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    version = models.PositiveIntegerField()
    content_markdown = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="post_revisions",
    )

    class Meta:
        ordering = ["-version"]
        unique_together = [("post", "version")]
        verbose_name = "Post Revision"
        verbose_name_plural = "Post Revisions"

    def __str__(self) -> str:
        return f"{self.post.title} (v{self.version})"


class InternalLink(TimeStampedModel, SoftDeleteModel):
    """
    Tracks internal links between posts for bidirectional navigation.

    Automatically generated when posts are saved by parsing markdown content.
    Enables backlinks feature: shows which posts link to the current post.
    """

    source_post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="outgoing_links",
        help_text="The post that contains the link",
    )
    target_post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="incoming_links",
        help_text="The post being linked to (these are the backlinks)",
    )
    link_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this post links to the target (if multiple links exist)",
    )

    # Managers
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["source_post"]),
            models.Index(fields=["target_post"]),
            models.Index(fields=["is_deleted", "source_post"]),
            models.Index(fields=["is_deleted", "target_post"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_post", "target_post"],
                name="unique_internal_link",
            ),
        ]
        verbose_name = "Internal Link"
        verbose_name_plural = "Internal Links"

    def __str__(self) -> str:
        return f"{self.source_post.title} → {self.target_post.title}"
