"""
Taxonomy models for organizing content.

Includes Tag (with hierarchical support and aliases), Category, and Series models.
"""

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.template.defaultfilters import slugify

from .base import TimeStampedModel


class TagQuerySet(models.QuerySet):
    """Custom queryset for Tag model."""

    def active(self):
        """Return only active tags."""
        return self.filter(is_active=True)

    def by_namespace(self, namespace):
        """Filter by namespace."""
        return self.filter(namespace=namespace)

    def root_tags(self):
        """Return only root-level tags (no parent)."""
        return self.filter(parent__isnull=True)

    def children_of(self, parent_tag):
        """Return children of a specific tag."""
        return self.filter(parent=parent_tag)


class TagManager(models.Manager):
    """Custom manager for Tag model."""

    def get_queryset(self):
        return TagQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def by_namespace(self, namespace):
        return self.get_queryset().by_namespace(namespace)

    def get_or_create_normalized(self, name, defaults=None):
        """
        Get or create a tag with normalized name (case-insensitive).
        Returns (tag, created) tuple.
        """
        normalized_name = self.model.normalize_name(name)
        defaults = defaults or {}

        # Try to find existing tag (case-insensitive)
        try:
            tag = self.get(name__iexact=normalized_name)
            return tag, False
        except self.model.DoesNotExist:
            # Create new tag with normalized name
            defaults['name'] = normalized_name
            tag = self.create(**defaults)
            return tag, True


class Tag(TimeStampedModel):
    """
    Hierarchical tagging system with namespaces, aliases, and rich metadata.

    Features:
    - Parent/child relationships for nested taxonomies
    - Namespaces for organizing tags (e.g., 'category:', 'tech:', 'location:')
    - Case-insensitive names with normalization
    - Visual styling (colors, icons)
    - Active/inactive state
    - Ranking/weighting for future sorting
    - Usage tracking
    - Tag aliases for synonyms
    """

    # Core fields
    name = models.CharField(
        max_length=64,
        help_text="Tag name (case-insensitive, normalized on save)",
    )
    slug = models.SlugField(
        max_length=80,
        unique=True,
        blank=True,
        help_text="URL-friendly identifier",
    )

    # Hierarchical relationship
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        help_text="Parent tag for hierarchical organization",
    )

    # Namespace for organization
    namespace = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        help_text="Optional namespace for grouping (e.g., 'tech', 'location', 'topic')",
    )

    # Rich metadata
    description = models.TextField(
        blank=True,
        help_text="Detailed description of what this tag represents",
    )

    # Visual styling
    color = models.CharField(
        max_length=7,
        default="#6B7280",
        help_text="Hex color for visual distinction (e.g., #3B82F6)",
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon identifier (e.g., Material icon name, emoji, or font-awesome class)",
    )

    # State and ranking
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this tag is active and available for use",
    )
    rank = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Priority/weight for sorting (higher = more important). Use for featured tags.",
    )

    # Usage tracking
    usage_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Number of times this tag has been used (cached)",
    )

    # Custom manager
    objects = TagManager()

    class Meta:
        ordering = ["-rank", "namespace", "name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["namespace", "name"]),
            models.Index(fields=["parent", "name"]),
            models.Index(fields=["is_active", "-usage_count"]),
            models.Index(fields=["-rank", "name"]),
        ]
        constraints = [
            # Ensure name is unique within namespace (case-insensitive)
            models.UniqueConstraint(
                fields=["namespace", "name"],
                name="unique_tag_namespace_name",
            ),
            # Prevent self-referencing parent
            models.CheckConstraint(
                check=~models.Q(parent=models.F("id")),
                name="tag_no_self_parent",
            ),
        ]

    def __str__(self) -> str:
        if self.namespace:
            return f"{self.namespace}:{self.name}"
        return self.name

    @property
    def full_name(self) -> str:
        """Return fully qualified name with namespace."""
        if self.namespace:
            return f"{self.namespace}:{self.name}"
        return self.name

    @property
    def breadcrumb(self) -> str:
        """Return hierarchical path (e.g., 'Technology > Python > Django')."""
        parts = []
        current = self
        while current:
            parts.insert(0, current.name)
            current = current.parent
        return " > ".join(parts)

    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalize tag name for consistency.
        - Strips whitespace
        - Converts to title case
        - Removes extra spaces
        """
        if not name:
            return ""
        # Strip and normalize whitespace
        normalized = " ".join(name.strip().split())
        # Title case for consistency
        normalized = normalized.title()
        return normalized

    @staticmethod
    def normalize_namespace(namespace: str) -> str:
        """
        Normalize namespace.
        - Lowercase
        - Strip whitespace
        """
        if not namespace:
            return ""
        return namespace.strip().lower()

    def save(self, *args, **kwargs):
        # Normalize name (case-insensitive)
        self.name = self.normalize_name(self.name)

        # Normalize namespace
        if self.namespace:
            self.namespace = self.normalize_namespace(self.namespace)

        # Auto-generate slug from full name
        if not self.slug:
            if self.namespace:
                base = slugify(f"{self.namespace}-{self.name}") or "tag"
            else:
                base = slugify(self.name) or "tag"
            self.slug = self._unique_slug(base)

        super().save(*args, **kwargs)

    def _unique_slug(self, base: str) -> str:
        """Generate unique slug."""
        slug = base
        i = 2
        while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    def clean(self):
        """Validate tag data."""
        super().clean()

        # Prevent circular parent relationships
        if self.parent:
            current = self.parent
            visited = {self.pk} if self.pk else set()
            while current:
                if current.pk in visited:
                    raise ValidationError(
                        {"parent": "Circular parent relationship detected"}
                    )
                visited.add(current.pk)
                current = current.parent

        # Validate color format
        if self.color and not re.match(r"^#[0-9A-Fa-f]{6}$", self.color):
            raise ValidationError(
                {"color": "Color must be in hex format (e.g., #3B82F6)"}
            )

    def get_descendants(self, include_self=False):
        """
        Get all descendant tags recursively.
        Returns queryset of all children, grandchildren, etc.
        """
        descendants = []
        if include_self:
            descendants.append(self.pk)

        def collect_children(tag):
            for child in tag.children.all():
                descendants.append(child.pk)
                collect_children(child)

        collect_children(self)
        return Tag.objects.filter(pk__in=descendants)

    def get_ancestors(self, include_self=False):
        """
        Get all ancestor tags up the hierarchy.
        Returns list of tags from immediate parent to root.
        """
        ancestors = []
        if include_self:
            ancestors.append(self)

        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent

        return ancestors

    def update_usage_count(self):
        """Update the cached usage count from actual relationships."""
        self.usage_count = self.posts.count()
        self.save(update_fields=["usage_count"])


class TagAlias(TimeStampedModel):
    """
    Tag aliases for handling synonyms and alternative names.

    Allows multiple names to map to the same canonical tag.
    Example: "ML" and "Machine Learning" both map to canonical tag "Machine Learning"
    """

    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name="aliases",
        help_text="The canonical tag this alias points to",
    )
    alias = models.CharField(
        max_length=64,
        unique=True,
        help_text="Alternative name for the tag (case-insensitive)",
    )
    slug = models.SlugField(
        max_length=80,
        unique=True,
        blank=True,
        help_text="URL-friendly identifier for the alias",
    )

    class Meta:
        ordering = ["alias"]
        verbose_name = "Tag Alias"
        verbose_name_plural = "Tag Aliases"
        indexes = [
            models.Index(fields=["alias"]),
            models.Index(fields=["tag", "alias"]),
        ]

    def __str__(self) -> str:
        return f"{self.alias} → {self.tag.name}"

    @staticmethod
    def normalize_alias(alias: str) -> str:
        """Normalize alias using same rules as Tag.normalize_name."""
        return Tag.normalize_name(alias)

    def save(self, *args, **kwargs):
        # Normalize alias
        self.alias = self.normalize_alias(self.alias)

        # Auto-generate slug
        if not self.slug:
            base = slugify(self.alias) or "alias"
            self.slug = self._unique_slug(base)

        super().save(*args, **kwargs)

    def _unique_slug(self, base: str) -> str:
        """Generate unique slug."""
        slug = base
        i = 2
        while TagAlias.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    def clean(self):
        """Validate alias doesn't conflict with existing tag names."""
        super().clean()

        # Check if alias conflicts with an existing tag name (case-insensitive)
        if Tag.objects.filter(name__iexact=self.alias).exists():
            raise ValidationError(
                {"alias": f"An alias cannot have the same name as an existing tag: '{self.alias}'"}
            )


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
