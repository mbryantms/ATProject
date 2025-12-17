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
    def get_queryset(self):
        return PostQuerySet(self.model, using=self._db).alive()


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
        "engine.Series", null=True, blank=True, on_delete=models.SET_NULL, related_name="posts"
    )
    categories = models.ManyToManyField("engine.Category", blank=True, related_name="posts")
    tags = models.ManyToManyField("engine.Tag", blank=True, related_name="posts")
    related_posts = models.ManyToManyField(
        "self", blank=True, symmetrical=False, related_name="related_to"
    )

    # --- Media ---
    # hero_image = models.ImageField(upload_to="posts/hero/", null=True, blank=True)
    # thumbnail_image = models.ImageField(upload_to="posts/thumbs/", null=True, blank=True)
    # hero_image_url = models.URLField(blank=True)
    # thumbnail_image_url = models.URLField(blank=True)
    # image_alt = models.CharField(max_length=200, blank=True)

    # --- SEO / Social ---
    # canonical_url = models.URLField(blank=True)
    # meta_title = models.CharField(max_length=255, blank=True)
    # meta_description = models.CharField(max_length=300, blank=True)
    # og_title = models.CharField(max_length=255, blank=True)
    # og_description = models.CharField(max_length=300, blank=True)
    # og_image_url = models.URLField(blank=True)
    # twitter_card = models.CharField(max_length=20, blank=True, help_text="e.g., summary, summary_large_image")
    # noindex = models.BooleanField(default=False)
    # nofollow = models.BooleanField(default=False)
    # schema_org = models.JSONField(blank=True, null=True)

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
                check=(
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
        is_new = self.pk is None
        if is_new:
            run_async_tasks = True
        else:
            try:
                # Fetch the original object from DB
                original = Post.objects.get(pk=self.pk)
                if original.content_markdown != self.content_markdown:
                    run_async_tasks = True
                    # Clear stale content that will be regenerated
                    self.table_of_contents = []
            except Post.DoesNotExist:
                # This case is unlikely but good to handle
                run_async_tasks = True

        # --- Update fast-running derived stats synchronously ---
        self.word_count = self._compute_word_count(self.content_markdown or "")
        self.reading_time_minutes = max(1, round(self.word_count / 225.0 + 0.0001))

        # --- Save the model ---
        super().save(*args, **kwargs)

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
        self, *, backlinks_count: int = 0, similar_posts_count: int = 0
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
        unique_together = [["source_post", "target_post"]]
        indexes = [
            models.Index(fields=["source_post"]),
            models.Index(fields=["target_post"]),
            models.Index(fields=["is_deleted", "source_post"]),
            models.Index(fields=["is_deleted", "target_post"]),
        ]
        verbose_name = "Internal Link"
        verbose_name_plural = "Internal Links"

    def __str__(self) -> str:
        return f"{self.source_post.title} → {self.target_post.title}"
