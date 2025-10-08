# models.py
import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.template.defaultfilters import slugify
from django.urls import reverse, NoReverseMatch
from django.utils import timezone

from engine.markdown.extensions.toc_extractor import extract_toc_from_html
from engine.markdown.renderer import render_markdown


# ---------------------------
# Base / Mixins
# ---------------------------


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()  # includes soft-deleted

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, soft: bool = True):
        if soft:
            self.is_deleted = True
            self.deleted_at = timezone.now()
            update_fields = ["is_deleted", "deleted_at"]
            if hasattr(self, "updated_at"):
                update_fields.append("updated_at")
            self.save(update_fields=update_fields)
        else:
            super().delete(using=using, keep_parents=keep_parents)


# ---------------------------
# Taxonomy
# ---------------------------


class Tag(TimeStampedModel):
    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "tag"
            self.slug = self._unique_slug(base)
        super().save(*args, **kwargs)

    def _unique_slug(self, base: str) -> str:
        slug = base
        i = 2
        while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug


class Category(TimeStampedModel):
    """Hierarchical category (optional parent)."""

    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "category"
            self.slug = self._unique_slug(base)
        super().save(*args, **kwargs)

    def _unique_slug(self, base: str) -> str:
        slug = base
        i = 2
        while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug


class Series(TimeStampedModel):
    """Optional grouping for multipart posts."""

    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["title"]
        verbose_name_plural = "series"

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "series"
            self.slug = self._unique_slug(base)
        super().save(*args, **kwargs)

    def _unique_slug(self, base: str) -> str:
        slug = base
        i = 2
        while Series.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug


# ---------------------------
# Post
# ---------------------------


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


class Post(TimeStampedModel, SoftDeleteModel):
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
        help_text="Optional article abstract in markdown (longer-form description, similar to journal article abstract)."
    )

    show_toc = models.BooleanField(
        default=False, help_text="Optionally show table of contents."
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
        Series, null=True, blank=True, on_delete=models.SET_NULL, related_name="posts"
    )
    categories = models.ManyToManyField(Category, blank=True, related_name="posts")
    tags = models.ManyToManyField(Tag, blank=True, related_name="posts")
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

    # Managers
    objects = PostManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-is_pinned", "pin_order", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["visibility", "published_at"]),
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
        # Update derived stats from Markdown only (no rendering here)
        self.word_count = self._compute_word_count(self.content_markdown or "")
        self.reading_time_minutes = max(1, round(self.word_count / 225.0 + 0.0001))
        html = render_markdown(self.content_markdown or "")
        self.table_of_contents = extract_toc_from_html(html)
        super().save(*args, **kwargs)

    def clean(self):
        if self.expire_at and self.published_at and self.expire_at <= self.published_at:
            from django.core.exceptions import ValidationError

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

    def get_absolute_url(self) -> str:
        try:
            return reverse("post-detail", kwargs={"slug": self.slug})
        except NoReverseMatch:
            return f"/posts/{self.slug}/"

    def _unique_slug(self, base: str) -> str:
        slug = base
        i = 2
        while Post.all_objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    @staticmethod
    def _compute_word_count(text: str) -> int:
        if not text:
            return 0
        return len(re.findall(r"\w+", text))


# ---------------------------
# Internal Links (Backlinks)
# ---------------------------


class InternalLink(TimeStampedModel, SoftDeleteModel):
    """
    Tracks internal links between posts for bidirectional navigation.

    Automatically generated when posts are saved by parsing markdown content.
    Enables backlinks feature: shows which posts link to the current post.
    """

    source_post = models.ForeignKey(
        'Post',
        on_delete=models.CASCADE,
        related_name='outgoing_links',
        help_text="The post that contains the link"
    )
    target_post = models.ForeignKey(
        'Post',
        on_delete=models.CASCADE,
        related_name='incoming_links',
        help_text="The post being linked to (these are the backlinks)"
    )
    link_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this post links to the target (if multiple links exist)"
    )

    # Managers
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        unique_together = [['source_post', 'target_post']]
        indexes = [
            models.Index(fields=['source_post']),
            models.Index(fields=['target_post']),
            models.Index(fields=['is_deleted', 'source_post']),
            models.Index(fields=['is_deleted', 'target_post']),
        ]
        verbose_name = "Internal Link"
        verbose_name_plural = "Internal Links"

    def __str__(self) -> str:
        return f"{self.source_post.title} → {self.target_post.title}"


# ---------------------------
# Asset Management System
# ---------------------------


class AssetQuerySet(SoftDeleteQuerySet):
    """Custom queryset with optimizations and filters."""

    def with_asset_tags(self):
        """Prefetch asset tags to avoid N+1 queries."""
        return self.prefetch_related("asset_tags")

    def with_usage(self):
        """Prefetch post usages."""
        return self.prefetch_related("post_usages", "post_usages__post")

    def by_type(self, asset_type):
        """Filter by asset type."""
        return self.filter(asset_type=asset_type)

    def images(self):
        """Get only images."""
        return self.filter(asset_type="image")

    def videos(self):
        """Get only videos."""
        return self.filter(asset_type="video")

    def ready(self):
        """Get only ready assets."""
        return self.filter(status="ready")


    def search(self, query):
        """Full-text search across relevant fields."""
        return self.filter(
            Q(key__icontains=query)
            | Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(alt_text__icontains=query)
            | Q(caption__icontains=query)
            | Q(credit__icontains=query)
        )


class AssetManager(SoftDeleteManager):
    """Custom manager for Asset model."""

    def get_queryset(self):
        return AssetQuerySet(self.model, using=self._db).alive()


class Asset(TimeStampedModel, SoftDeleteModel):
    """
    Global asset library for all media types.

    Assets are reusable across posts and have global keys for markdown reference.
    """

    ASSET_TYPES = [
        ("image", "Image"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("document", "Document"),
        ("archive", "Archive"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("uploading", "Uploading"),
        ("processing", "Processing"),
        ("ready", "Ready"),
        ("failed", "Failed"),
        ("archived", "Archived"),
    ]

    # Status choices
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready for Use"
        ARCHIVED = "archived", "Archived"

    # Core Fields
    key = models.SlugField(
        max_length=200,
        unique=True,
        blank=True,
        help_text="Global unique key for markdown reference. Leave blank for auto-generation with smart prefixes. "
        "Use in markdown as @asset:key",
    )

    title = models.CharField(max_length=255, help_text="Human-readable title")

    asset_type = models.CharField(
        max_length=20,
        choices=ASSET_TYPES,
        help_text="Type of asset (auto-detected from file extension)",
    )

    file = models.FileField(
        upload_to="assets/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "jpg",
                    "jpeg",
                    "png",
                    "gif",
                    "webp",
                    "svg",
                    "bmp",
                    "ico",  # images
                    "mp4",
                    "webm",
                    "mov",
                    "avi",
                    "mkv",
                    "m4v",  # video
                    "mp3",
                    "wav",
                    "ogg",
                    "m4a",
                    "flac",
                    "aac",  # audio
                    "pdf",
                    "epub",
                    "doc",
                    "docx",
                    "txt",
                    "md",  # documents
                    "csv",
                    "json",
                    "xml",
                    "jsonl",
                    "tsv",
                    "yaml",
                    "yml",  # data
                ]
            )
        ],
        help_text="The asset file (max: 100MB for images, 500MB for videos)",
    )

    original_filename = models.CharField(
        max_length=255, blank=True, help_text="Original filename when uploaded"
    )

    file_extension = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        help_text="File extension (e.g., 'jpg', 'mp4')",
    )

    # Metadata
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        help_text="Alternative text for accessibility (required for images)",
    )

    caption = models.TextField(blank=True, help_text="Caption to display with asset")

    description = models.TextField(
        blank=True, help_text="Detailed description for admin/search"
    )

    credit = models.CharField(
        max_length=255,
        blank=True,
        help_text="Credit/attribution (e.g., 'Photo by John Doe')",
    )

    license = models.CharField(
        max_length=100, blank=True, help_text="License information (e.g., 'CC BY 4.0')"
    )

    # File metadata (auto-populated)
    file_size = models.PositiveIntegerField(
        null=True, blank=True, help_text="File size in bytes"
    )

    mime_type = models.CharField(
        max_length=100, blank=True, help_text="MIME type (e.g., 'image/jpeg')"
    )

    width = models.PositiveIntegerField(
        null=True, blank=True, help_text="Width in pixels (for images/videos)"
    )

    height = models.PositiveIntegerField(
        null=True, blank=True, help_text="Height in pixels (for images/videos)"
    )

    duration = models.DurationField(
        null=True, blank=True, help_text="Duration (for audio/video)"
    )

    bitrate = models.PositiveIntegerField(
        null=True, blank=True, help_text="Bitrate in kbps (for audio/video)"
    )

    frame_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Frame rate in fps (for video)",
    )

    # File hash for deduplication
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA256 hash for deduplication",
    )

    # Organization and workflow
    is_public = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this asset is publicly accessible",
    )

    permissions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom permissions for this asset (e.g., user/group access)",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.READY,
        db_index=True,
        help_text="Asset status workflow",
    )

    source_url = models.URLField(
        blank=True, help_text="Original source URL if asset was imported"
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_assets",
        help_text="User who uploaded this asset",
    )

    # Focal point for smart cropping (0.0 to 1.0)
    focal_point_x = models.FloatField(
        null=True, blank=True, help_text="X coordinate (0.0-1.0) for image focal point"
    )

    focal_point_y = models.FloatField(
        null=True, blank=True, help_text="Y coordinate (0.0-1.0) for image focal point"
    )

    # Organization fields
    asset_folder = models.ForeignKey(
        "AssetFolder",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="folder_assets",
        help_text="Folder this asset belongs to",
    )

    asset_tags = models.ManyToManyField(
        "AssetTag",
        blank=True,
        related_name="tagged_assets",
        help_text="Asset-specific tags (separate from post tags)",
    )

    # Usage and analytics tracking
    usage_count = models.PositiveIntegerField(
        default=0, help_text="Number of posts using this asset"
    )

    view_count = models.PositiveIntegerField(
        default=0, help_text="Number of times this asset has been viewed"
    )

    download_count = models.PositiveIntegerField(
        default=0, help_text="Number of times this asset has been downloaded"
    )

    last_accessed = models.DateTimeField(
        null=True, blank=True, help_text="Last time this asset was accessed/viewed"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key"]),
            models.Index(fields=["asset_type", "-created_at"]),
            models.Index(fields=["is_deleted", "asset_type"]),
            models.Index(fields=["file_hash"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["uploaded_by", "-created_at"]),
            models.Index(fields=["file_extension", "asset_type"]),
            models.Index(fields=["is_public", "status"]),
            models.Index(fields=["-last_accessed"]),
            models.Index(fields=["-view_count"]),
            models.Index(fields=["-download_count"]),
            # GinIndex(fields=["search_vector"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(file_size__gte=0) | models.Q(file_size__isnull=True),
                name="asset_file_size_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(width__gte=0) | models.Q(width__isnull=True),
                name="asset_width_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(height__gte=0) | models.Q(height__isnull=True),
                name="asset_height_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(focal_point_x__gte=0.0, focal_point_x__lte=1.0)
                    | models.Q(focal_point_x__isnull=True)
                ),
                name="asset_focal_point_x_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(focal_point_y__gte=0.0, focal_point_y__lte=1.0)
                    | models.Q(focal_point_y__isnull=True)
                ),
                name="asset_focal_point_y_range",
            ),
        ]

    # Managers
    objects = AssetManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.title} - {self.get_asset_type_display()} ({self.key})"

    def clean(self):
        """Validate asset fields."""
        super().clean()

        # Validate file size based on type
        if self.file and hasattr(self.file, "size"):
            max_sizes = {
                "image": 100 * 1024 * 1024,  # 100MB
                "video": 500 * 1024 * 1024,  # 500MB
                "audio": 50 * 1024 * 1024,  # 50MB
                "document": 50 * 1024 * 1024,
                "archive": 10 * 1024 * 1024,
                "other": 100 * 1024 * 1024,
            }
            max_size = max_sizes.get(self.asset_type, 100 * 1024 * 1024)
            if self.file.size > max_size:
                raise ValidationError(
                    {
                        "file": f"File size ({self.human_file_size}) exceeds maximum for {self.get_asset_type_display()}"
                    }
                )

        # Require alt_text for images (accessibility)
        if (
            self.asset_type == "image"
            and not self.alt_text
            and self.status == self.Status.READY
        ):
            raise ValidationError(
                {"alt_text": "Alternative text is required for images (accessibility)"}
            )

        # Validate focal point ranges
        if self.focal_point_x is not None and not (0.0 <= self.focal_point_x <= 1.0):
            raise ValidationError(
                {"focal_point_x": "Focal point X must be between 0.0 and 1.0"}
            )

        if self.focal_point_y is not None and not (0.0 <= self.focal_point_y <= 1.0):
            raise ValidationError(
                {"focal_point_y": "Focal point Y must be between 0.0 and 1.0"}
            )

    def _generate_unique_key(self, base_slug):
        """
        Generate a unique key with intelligent organization.

        Format: [collection/][type-]base[-suffix]
        Examples:
            - blog-2024/img-sunset-beach
            - diagrams/img-revenue-chart-a7f8
            - video-tutorial-intro
        """
        import secrets

        parts = []

        # Add type prefix for better organization
        type_prefixes = {
            "image": "img",
            "video": "vid",
            "audio": "aud",
            "document": "doc",
            "archive": "arc",
            "other": "asset",
        }
        type_prefix = type_prefixes.get(self.asset_type, "asset")

        # Construct base key
        if parts:
            # collection/type-slug format
            base_key = f"{'/'.join(parts)}/{type_prefix}-{base_slug}"
        else:
            # type-slug format
            base_key = f"{type_prefix}-{base_slug}"

        # Check if base key is unique
        if not Asset.objects.filter(key=base_key).exclude(pk=self.pk).exists():
            return base_key

        # If not unique, add short hash suffix
        # Try without collection first (for backwards compatibility)
        simple_key = f"{type_prefix}-{base_slug}"
        if (
            not parts
            and not Asset.objects.filter(key=simple_key).exclude(pk=self.pk).exists()
        ):
            return simple_key

        # Add 4-character random suffix for uniqueness
        for _ in range(10):  # Try up to 10 times
            suffix = secrets.token_hex(2)  # 4 characters
            unique_key = f"{base_key}-{suffix}"
            if not Asset.objects.filter(key=unique_key).exclude(pk=self.pk).exists():
                return unique_key

        # Fallback: use timestamp-based suffix
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{base_key}-{timestamp}"

    def save(self, *args, **kwargs):
        # Store original filename if not already set
        if self.file and not self.original_filename:
            import os

            self.original_filename = os.path.basename(self.file.name)

        # Store file extension
        if self.file and not self.file_extension:
            import os

            ext = os.path.splitext(self.file.name)[1].lower()
            self.file_extension = ext.lstrip(".")  # Remove leading dot

        # Auto-detect asset type from file extension first (needed for key generation)
        if self.file and not self.asset_type:
            self.asset_type = self.detect_asset_type()

        # Auto-generate organized key from title if not provided
        if not self.key and self.title:
            base_slug = slugify(self.title) or "asset"
            self.key = self._generate_unique_key(base_slug)

        # Calculate file hash for deduplication
        if self.file and not self.file_hash:
            import hashlib

            try:
                self.file.seek(0)
                file_hash = hashlib.sha256(self.file.read()).hexdigest()
                self.file_hash = file_hash
                self.file.seek(0)
            except Exception:
                pass  # Skip if file can't be read

        # Auto-populate file metadata
        if self.file:
            self.populate_file_metadata()

        # Determine if this is a new asset
        is_new = self.pk is None

        super().save(*args, **kwargs)

        # Trigger async metadata extraction for new assets
        if is_new and self.file:
            from .tasks import extract_metadata_async

            extract_metadata_async.delay(self.pk)

    def detect_asset_type(self):
        """Detect asset type from file extension."""
        import os

        ext = os.path.splitext(self.file.name)[1].lower()

        image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"]
        video_exts = [".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"]
        audio_exts = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]
        document_exts = [".pdf", ".epub", ".doc", ".docx", ".txt", ".md"]
        archive_exts = [".zip", ".tar", ".gz", ".bz2", ".7z", ".rar"]

        if ext in image_exts:
            return "image"
        elif ext in video_exts:
            return "video"
        elif ext in audio_exts:
            return "audio"
        elif ext in document_exts:
            return "document"
        elif ext in archive_exts:
            return "archive"

        return "other"  # Default

    def populate_file_metadata(self):
        """Populate file size and MIME type."""
        if self.file:
            self.file_size = self.file.size

            # Detect MIME type
            import mimetypes

            mime_type, _ = mimetypes.guess_type(self.file.name)
            if mime_type:
                self.mime_type = mime_type

            # Populate dimensions for images
            if self.asset_type == "image" and hasattr(self.file, "path"):
                try:
                    from PIL import Image

                    with Image.open(self.file.path) as img:
                        self.width, self.height = img.size
                except Exception:
                    pass

    @property
    def url(self):
        """Get URL for asset (file.url for now, can be extended for CDN)."""
        if self.file:
            return self.file.url
        return ""

    @property
    def markdown_reference(self):
        """Get markdown reference string."""
        return f"@asset:{self.key}"

    @property
    def human_file_size(self):
        """Get human-readable file size."""
        if not self.file_size:
            return "Unknown"

        size = float(self.file_size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class AssetMetadata(TimeStampedModel):
    """
    Extended metadata for assets including EXIF, color, and media-specific information.
    """

    asset = models.OneToOneField(
        Asset,
        on_delete=models.CASCADE,
        related_name="metadata",
        primary_key=True,
        help_text="Asset this metadata belongs to",
    )

    # EXIF and technical metadata
    exif_data = models.JSONField(
        blank=True, null=True, help_text="Raw EXIF data from image"
    )

    # Camera metadata (images)
    camera_make = models.CharField(
        max_length=100,
        blank=True,
        help_text="Camera manufacturer (e.g., 'Canon', 'Nikon')",
    )

    camera_model = models.CharField(
        max_length=100, blank=True, help_text="Camera model (e.g., 'EOS 5D Mark IV')"
    )

    lens = models.CharField(
        max_length=100,
        blank=True,
        help_text="Lens used (e.g., 'EF 24-70mm f/2.8L II USM')",
    )

    focal_length = models.FloatField(
        null=True, blank=True, help_text="Focal length in mm"
    )

    aperture = models.FloatField(
        null=True, blank=True, help_text="Aperture f-stop (e.g., 2.8, 5.6)"
    )

    shutter_speed = models.CharField(
        max_length=50, blank=True, help_text="Shutter speed (e.g., '1/500', '2s')"
    )

    iso = models.IntegerField(null=True, blank=True, help_text="ISO sensitivity")

    captured_at = models.DateTimeField(
        null=True, blank=True, help_text="Date and time the photo/video was captured"
    )

    # Location metadata (GPS)
    latitude = models.FloatField(null=True, blank=True, help_text="GPS latitude")

    longitude = models.FloatField(null=True, blank=True, help_text="GPS longitude")

    location_name = models.CharField(
        max_length=255, blank=True, help_text="Human-readable location name"
    )

    # Audio metadata
    artist = models.CharField(
        max_length=255, blank=True, help_text="Artist/performer name (audio)"
    )

    album = models.CharField(max_length=255, blank=True, help_text="Album name (audio)")

    genre = models.CharField(max_length=100, blank=True, help_text="Genre (audio)")

    year = models.IntegerField(
        null=True, blank=True, help_text="Year of creation/publication"
    )

    track_number = models.IntegerField(
        null=True, blank=True, help_text="Track number in album (audio)"
    )

    # Document metadata
    author = models.CharField(
        max_length=255, blank=True, help_text="Author/creator name (documents)"
    )

    subject = models.CharField(
        max_length=255, blank=True, help_text="Subject/topic (documents)"
    )

    keywords = models.TextField(
        blank=True, help_text="Keywords/tags from document metadata"
    )

    page_count = models.IntegerField(
        null=True, blank=True, help_text="Number of pages (documents)"
    )

    # Color information (images)
    dominant_colors = models.JSONField(
        blank=True,
        null=True,
        help_text="Dominant colors in the image (array of hex codes)",
    )

    color_palette = models.JSONField(
        blank=True, null=True, help_text="Color palette extracted from image"
    )

    average_color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Average color as hex code (e.g., '#FF5733')",
    )

    color_space = models.CharField(
        max_length=50,
        blank=True,
        help_text="Color space (e.g., 'sRGB', 'Adobe RGB', 'ProPhoto RGB')",
    )

    color_profile = models.CharField(
        max_length=100, blank=True, help_text="ICC color profile name"
    )

    # Image quality metadata
    dpi = models.IntegerField(
        null=True, blank=True, help_text="Dots per inch (DPI) for images"
    )

    has_alpha = models.BooleanField(
        default=False, help_text="Whether image has alpha channel (transparency)"
    )

    # Extensibility
    custom_fields = models.JSONField(
        blank=True,
        null=True,
        default=dict,
        help_text="Additional custom metadata fields",
    )

    class Meta:
        verbose_name = "Asset Metadata"
        verbose_name_plural = "Asset Metadata"
        indexes = [
            models.Index(fields=["camera_make", "camera_model"]),
            models.Index(fields=["captured_at"]),
            models.Index(fields=["artist", "album"]),
            models.Index(fields=["author"]),
            models.Index(fields=["year"]),
        ]

    def __str__(self):
        return f"Metadata for {self.asset.key}"

    @property
    def has_gps(self):
        """Check if GPS coordinates are available."""
        return self.latitude is not None and self.longitude is not None

    @property
    def has_camera_info(self):
        """Check if camera metadata is available."""
        return bool(self.camera_make or self.camera_model)

    @property
    def has_audio_info(self):
        """Check if audio metadata is available."""
        return bool(self.artist or self.album)


class AssetRendition(TimeStampedModel):
    """
    Auto-generated renditions of assets (primarily for responsive images).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this rendition",
    )

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="renditions"
    )

    # Rendition specifications
    width = models.PositiveIntegerField(help_text="Width of this rendition")

    height = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Height of this rendition (may be auto-calculated)",
    )

    format = models.CharField(
        max_length=10, default="auto", help_text="Image format (jpeg, webp, auto)"
    )

    # Quality presets
    class Quality(models.TextChoices):
        LOW = "low", "Low (60%)"
        MEDIUM = "medium", "Medium (75%)"
        HIGH = "high", "High (85%)"
        MAX = "max", "Maximum (95%)"

    quality = models.CharField(
        max_length=10,
        choices=Quality.choices,
        default=Quality.HIGH,
        help_text="Compression quality",
    )

    # Preset names for easy reference (also known as size/rendition size)
    preset = models.CharField(
        max_length=50,
        blank=True,
        help_text="Preset/size name (e.g., 'thumbnail', 'hero', 'card', 'small', 'medium', 'large')",
    )

    file = models.ImageField(
        upload_to="assets/renditions/%Y/%m/", help_text="Rendition file"
    )

    file_size = models.PositiveIntegerField(help_text="File size in bytes")

    # Media-specific metadata
    bitrate = models.PositiveIntegerField(
        null=True, blank=True, help_text="Bitrate in kbps (for video/audio renditions)"
    )

    codec = models.CharField(
        max_length=50,
        blank=True,
        help_text="Codec used for encoding (e.g., 'h264', 'vp9', 'aac')",
    )

    # CDN delivery
    cdn_url = models.URLField(
        blank=True,
        max_length=500,
        help_text="CDN URL for this rendition (if using external CDN)",
    )

    # Track generation status
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
        help_text="Generation status",
    )

    error_message = models.TextField(
        blank=True, help_text="Error message if generation failed"
    )

    # WebP flag
    is_webp = models.BooleanField(default=False, help_text="Is this a WebP rendition")

    class Meta:
        ordering = ["width"]
        unique_together = ["asset", "width", "format", "quality"]
        indexes = [
            models.Index(fields=["asset", "width", "format"]),
            models.Index(fields=["status"]),
            models.Index(fields=["preset", "asset"]),
            models.Index(fields=["codec", "format"]),
        ]

    def __str__(self):
        preset_info = f" [{self.preset}]" if self.preset else ""
        return f"{self.asset.key} - {self.width}w ({self.format}){preset_info}"

    @property
    def url(self):
        """Get URL for this rendition (CDN URL if available, otherwise file URL)."""
        if self.cdn_url:
            return self.cdn_url
        if self.file:
            return self.file.url
        return ""

    @property
    def human_file_size(self):
        """Get human-readable file size."""
        if not self.file_size:
            return "Unknown"

        size = float(self.file_size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class PostAsset(TimeStampedModel):
    """
    Association between posts and assets with optional per-post aliases.
    """

    post = models.ForeignKey(
        "Post", on_delete=models.CASCADE, related_name="post_assets"
    )

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="post_usages"
    )

    alias = models.SlugField(
        max_length=100,
        blank=True,
        help_text="Optional short alias for this post (e.g., 'diagram1' → 'diagram-2024-revenue'). "
        "Use in markdown as @alias",
    )

    # Ordering for display
    order = models.PositiveIntegerField(default=0, help_text="Display order in admin")

    # Override metadata per post (optional)
    custom_caption = models.TextField(
        blank=True, help_text="Override default caption for this post"
    )

    custom_alt_text = models.CharField(
        max_length=255, blank=True, help_text="Override default alt text for this post"
    )

    class Meta:
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["post", "order"]),
            models.Index(fields=["post", "asset"]),
        ]
        constraints = [
            # Only enforce unique alias when it's not blank
            models.UniqueConstraint(
                fields=["post", "alias"],
                condition=~models.Q(alias=""),
                name="unique_post_alias_when_not_blank",
            ),
        ]

    def __str__(self):
        alias_str = f" (alias: @{self.alias})" if self.alias else ""
        return f"{self.post.title} → {self.asset.key}{alias_str}"

    @property
    def markdown_reference(self):
        """Get markdown reference string (prefers alias if available)."""
        if self.alias:
            return f"@{self.alias}"
        return f"@asset:{self.asset.key}"

    def get_caption(self):
        """Get caption (custom or default)."""
        return self.custom_caption or self.asset.caption

    def get_alt_text(self):
        """Get alt text (custom or default)."""
        return self.custom_alt_text or self.asset.alt_text


# ---------------------------
# Asset Organization Models
# ---------------------------


class AssetFolder(TimeStampedModel):
    """Hierarchical folder structure for organizing assets."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Folder name")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        help_text="Parent folder (null for root folders)",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="asset_folders",
        help_text="Folder owner",
    )

    path = models.CharField(
        max_length=1000, editable=False, help_text="Computed full path"
    )

    class Meta:
        unique_together = [["user", "parent", "name"]]
        ordering = ["path"]
        verbose_name = "Asset Folder"
        verbose_name_plural = "Asset Folders"

    def __str__(self):
        return self.path

    def save(self, *args, **kwargs):
        """Auto-compute path on save."""
        if self.parent:
            self.path = f"{self.parent.path}/{self.name}"
        else:
            self.path = self.name
        super().save(*args, **kwargs)


class AssetTag(models.Model):
    """Tags for asset categorization (separate from post tags)."""

    name = models.CharField(max_length=50, unique=True, help_text="Tag name")
    slug = models.SlugField(unique=True, help_text="URL-friendly tag identifier")
    color = models.CharField(
        max_length=7,
        default="#3B82F6",
        help_text="Hex color for visual distinction (e.g., #3B82F6)",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Asset Tag"
        verbose_name_plural = "Asset Tags"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Auto-generate slug from name if not provided."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class AssetCollection(TimeStampedModel):
    """Curated collections of assets for better organization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Collection name")
    description = models.TextField(blank=True, help_text="Collection description")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="asset_collections",
        help_text="Collection owner",
    )

    is_public = models.BooleanField(
        default=False, help_text="Whether this collection is publicly visible"
    )
    cover_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Cover image for this collection",
    )

    # Many-to-many relationship with assets
    assets = models.ManyToManyField(
        Asset,
        blank=True,
        related_name="collections",
        help_text="Assets in this collection",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Asset Collection"
        verbose_name_plural = "Asset Collections"

    def __str__(self):
        return self.name

    def asset_count(self):
        """Return the number of assets in this collection."""
        return self.assets.count()
