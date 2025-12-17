"""
Base models and mixins for the engine app.

Provides foundational model classes and manager/queryset patterns used across the application.
"""

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base model that adds created_at and updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """Custom queryset for soft-delete functionality."""

    def alive(self):
        """Return only non-deleted objects."""
        return self.filter(is_deleted=False)

    def deleted(self):
        """Return only soft-deleted objects."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager that returns only non-deleted objects by default."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class SoftDeleteModel(models.Model):
    """Abstract base model that adds soft-delete functionality."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()  # includes soft-deleted

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, soft: bool = True):
        """
        Delete the object.

        Args:
            using: Database alias to use
            keep_parents: Whether to keep parent objects
            soft: If True, soft delete. If False, hard delete from database.
        """
        if soft:
            self.is_deleted = True
            self.deleted_at = timezone.now()
            update_fields = ["is_deleted", "deleted_at"]
            if hasattr(self, "updated_at"):
                update_fields.append("updated_at")
            self.save(update_fields=update_fields)
        else:
            super().delete(using=using, keep_parents=keep_parents)


class UniqueSlugMixin:
    """
    Mixin that provides a method to generate a unique slug for a model.

    Expects the model to have a 'slug' field.
    """

    def _unique_slug(self, base: str) -> str:
        """
        Generate a unique slug, appending a counter if needed.

        This method checks for slug uniqueness across all objects, including
        soft-deleted ones if the model supports it, to prevent future collisions.
        """
        slug = base
        counter = 2

        # Use 'all_objects' manager if it exists, otherwise default to 'objects'
        # This ensures uniqueness check includes soft-deleted items to prevent collisions.
        manager = getattr(self.__class__, "all_objects", self.__class__.objects)

        while manager.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{counter}"
            counter += 1

        return slug
