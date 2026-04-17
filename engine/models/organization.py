"""
Organization models for asset management.

Includes AssetFolder, AssetTag, and AssetCollection models for organizing assets.
"""

import uuid

from django.conf import settings
from django.db import models
from django.template.defaultfilters import slugify

from .base import TimeStampedModel


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
        ordering = ["path"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "parent", "name"],
                name="unique_asset_folder_path",
            ),
        ]
        verbose_name = "Asset Folder"
        verbose_name_plural = "Asset Folders"

    def __str__(self):
        return self.path

    def save(self, *args, **kwargs):
        """Auto-compute path and update descendant paths on rename."""
        is_new = self.pk is None
        old_path = None
        if not is_new:
            try:
                original = AssetFolder.objects.get(pk=self.pk)
                old_path = original.path
            except AssetFolder.DoesNotExist:
                is_new = True

        # Generate the new path
        if self.parent:
            self.path = f"{self.parent.path}/{self.name}"
        else:
            self.path = self.name

        super().save(*args, **kwargs)

        # If the path changed, batch-update all descendants in one query
        # instead of recursively calling save() on each child.
        if old_path is not None and old_path != self.path:
            prefix = old_path + "/"
            new_prefix = self.path + "/"
            # Update all descendants whose path starts with the old prefix.
            # Uses SQL CONCAT to replace the old prefix with the new one.
            from django.db.models import Value
            from django.db.models.functions import Concat, Substr

            descendants = AssetFolder.objects.filter(path__startswith=prefix)
            if descendants.exists():
                old_prefix_len = len(prefix)
                descendants.update(
                    path=Concat(
                        Value(new_prefix),
                        Substr("path", old_prefix_len + 1),
                    )
                )


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
        "engine.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Cover image for this collection",
    )

    # Many-to-many relationship with assets
    assets = models.ManyToManyField(
        "engine.Asset",
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
