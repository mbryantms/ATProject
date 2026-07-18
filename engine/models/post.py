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
            Q(expire_at__isnull=True) | Q(expire_at__gt=now),
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
            # completion_status is already indexed via db_index=True on the
            # field; a second Meta index on the same column was pure duplicate
            # write overhead.
            GinIndex(fields=["search_vector"], name="post_search_vector_gin"),
            # Partial index for the dominant public query — the archive, feeds,
            # and sitemap all filter to published + public + live and order by
            # -published_at (see PostQuerySet.published().public()). Indexing
            # only those rows keeps it small and write-cheap (it's only touched
            # when a published public post changes), while serving the ORDER BY
            # directly. The published_at <= now bound is a range scan on the
            # ordered column and so needs no static condition.
            models.Index(
                fields=["-published_at"],
                name="post_live_public_idx",
                condition=Q(
                    status="published",
                    visibility="public",
                    is_deleted=False,
                ),
            ),
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

        # --- Check for content / slug changes ---
        run_async_tasks = False
        content_changed = False
        old_slug = None
        is_new = self.pk is None
        if is_new:
            run_async_tasks = True
            content_changed = True
        else:
            try:
                # Fetch the original object from DB
                original = Post.all_objects.get(pk=self.pk)
                if original.slug and original.slug != self.slug:
                    old_slug = original.slug
                if original.content_markdown != self.content_markdown:
                    run_async_tasks = True
                    content_changed = True
                    self.version = original.version + 1
                    # Clear stale derived content that will be regenerated by
                    # ``update_post_derived_content``. Clearing the HTML cache
                    # (not just the TOC) means the detail template's live-render
                    # fallback serves fresh content if the async task is delayed
                    # or the broker is down — trading a slower render for
                    # correctness instead of serving the old body indefinitely.
                    self.table_of_contents = []
                    self.content_html_cached = ""
            except Post.DoesNotExist:
                # This case is unlikely but good to handle
                run_async_tasks = True
                content_changed = True

        # A published post must always carry a go-live time — the DB
        # CheckConstraint requires it, and the public `published()` queryset
        # filters on it. Stamp "now" for any save that sets PUBLISHED without a
        # time, so this holds regardless of the code path (admin, API, shell,
        # data import) rather than only when the admin remembers to set it.
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()

        # --- Update fast-running derived stats synchronously ---
        self.word_count = self._compute_word_count(self.content_markdown or "")
        self.reading_time_minutes = max(1, round(self.word_count / 225.0 + 0.0001))

        # --- Save the model ---
        super().save(*args, **kwargs)

        # --- Record the previous slug so old permalinks keep resolving ---
        if old_slug:
            # Drop any history row that collides with the now-current slug (a
            # slug can be reused after moving away from it) and record the old
            # one pointing at this post.
            PostSlugHistory.objects.filter(old_slug=self.slug).delete()
            PostSlugHistory.objects.update_or_create(
                old_slug=old_slug, defaults={"post": self}
            )

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
        # Guard the enqueue: if the broker is unreachable, .delay() raises, and
        # because this runs in an on_commit callback the row is already saved —
        # an unguarded failure would surface as a 500 on an otherwise-successful
        # save. The content_html_cached was cleared above, so the detail view's
        # live-render fallback keeps serving correct content until a worker runs.
        if run_async_tasks:

            def _enqueue_derived_content(pk=self.pk):
                try:
                    update_post_derived_content.delay(pk)
                except Exception:
                    import logging

                    logging.getLogger("engine").warning(
                        "Could not enqueue derived-content render for post %s "
                        "(broker unreachable?); serving live-rendered HTML until "
                        "a worker runs.",
                        pk,
                    )

            transaction.on_commit(_enqueue_derived_content)

    def clean(self):
        if self.expire_at and self.published_at and self.expire_at <= self.published_at:
            raise ValidationError(
                {"expire_at": "Expiration must be after the publish time."}
            )

    def publish(self, by=None):
        """Transition this post to published, stamping provenance once.

        Centralizes the publish rule (go-live time + publisher) so every caller
        — the admin bulk action, the API, a shell session — records the same
        provenance instead of it living only in the admin. ``save()`` fills in
        ``published_at`` if unset; ``published_by`` is recorded only the first
        time it goes live.
        """
        self.status = self.Status.PUBLISHED
        if by is not None and self.published_by is None:
            self.published_by = by
        self.save()

    # ---------------------------
    # Helpers
    # ---------------------------

    @property
    def is_published(self) -> bool:
        now = timezone.now()
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and self.published_at <= now
            and (self.expire_at is None or self.expire_at > now)
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
        """Return the best available OG image URL.

        Priority:
          1. Manual ``og_image_url`` override
          2. Manual ``hero_image_url`` override
          3. First post asset's ``social-wide`` rendition (1200x630, cropped
             to focal point) — this is what was generated exactly for this
             purpose.
          4. First post asset's plain 1200w rendition (legacy / pre-focal-crop
             assets).
          5. The original asset file as a last resort.

        Always prefer source-format ("auto") renditions for social URLs —
        some crawlers / link-preview services don't accept AVIF/WebP.
        """
        if self.og_image_url:
            return self.og_image_url
        if self.hero_image_url:
            return self.hero_image_url

        # Iterate the prefetched relations in Python rather than issuing fresh
        # .filter() queries. Both callers (the detail-view SEO context and the
        # feeds) prefetch ``post_assets__asset`` — feeds also prefetch
        # ``__renditions`` — so a 20-item feed no longer fires 2-3 asset queries
        # per item. post_assets/renditions keep their model-Meta ordering
        # (``order``/``width``), so "first matching" is identical to the prior
        # ``.filter(...).first()`` result.
        first_image = None
        for post_asset in self.post_assets.all():
            asset = post_asset.asset
            if asset and asset.asset_type == "image" and asset.status == "ready":
                first_image = post_asset
                break
        if not first_image:
            return ""

        renditions = list(first_image.asset.renditions.all())

        # 1200x630 social crop, source format (JPEG/PNG — most crawler-safe).
        social = next(
            (
                r
                for r in renditions
                if r.preset == "social-wide"
                and r.format == "auto"
                and r.status == "completed"
            ),
            None,
        )
        if social:
            return social.url

        # Plain 1200w base rendition, source format.
        base = next(
            (
                r
                for r in renditions
                if r.preset == ""
                and r.width == 1200
                and r.format == "auto"
                and r.status == "completed"
            ),
            None,
        )
        if base:
            return base.url

        return first_image.asset.url

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
        Return posts ranked for similarity, reading from the precomputed
        ``PostSimilarity`` table. ``include_private`` can be used for staff
        tools.
        """
        qs = (
            PostSimilarity.objects.filter(source_post=self)
            .select_related("target_post")
            .order_by("-score", "-target_post__published_at")
        )
        if min_score is not None:
            qs = qs.filter(score__gte=min_score)
        visibilities = [Post.Visibility.PUBLIC, Post.Visibility.UNLISTED]
        if include_private:
            visibilities.append(Post.Visibility.PRIVATE)
        qs = qs.filter(
            target_post__status=Post.Status.PUBLISHED,
            target_post__is_deleted=False,
            target_post__visibility__in=visibilities,
        )
        return [sim.target_post for sim in qs[:limit]]

    @staticmethod
    def _compute_word_count(text: str) -> int:
        if not text:
            return 0
        return len(re.findall(r"\w+", text))


class PostSlugHistory(models.Model):
    """Maps a post's previous slugs to the post, so old permalinks 301-redirect.

    A row is created in ``Post.save()`` whenever a post's slug changes. The
    detail view falls back to this table on a 404 and permanently redirects to
    the post's current URL, so renaming a published post no longer breaks
    inbound links, bookmarks, or shared URLs.
    """

    old_slug = models.SlugField(max_length=220, unique=True, db_index=True)
    post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="slug_history",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Post Slug History"
        verbose_name_plural = "Post Slug History"

    def __str__(self) -> str:
        return f"{self.old_slug} → {self.post.slug}"


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


class PostSimilarity(models.Model):
    """
    Precomputed similarity rows per (source_post, target_post) pair.

    Refreshed by the ``recompute_similarity_for_post`` Celery task on
    post/tag/category/InternalLink/PostCitation changes. Asymmetric: a row
    from A→B does not imply B→A, since anchor-post context affects scoring.
    """

    source_post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="similar_outgoing",
    )
    target_post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="similar_incoming",
    )
    score = models.FloatField()
    components = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["source_post", "-score"],
                name="postsim_source_score_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_post", "target_post"],
                name="unique_post_similarity",
            ),
        ]
        verbose_name = "Post Similarity"
        verbose_name_plural = "Post Similarities"

    def __str__(self) -> str:
        return f"{self.source_post_id} ≈ {self.target_post_id} ({self.score:.3f})"
