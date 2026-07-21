"""
PostCitation model — tracks which sources are cited in which posts.

This is a through/join table derived from the rendered content (the markdown
is the source of truth). Having it in the database enables queries like
"which posts cite this source?" and "show all sources cited across the site."
"""

from django.db import models

from .base import TimeStampedModel


class PostCitation(TimeStampedModel):
    """
    Links a Post to a Source that is cited in its content.

    Created/updated automatically when a post's markdown is rendered.
    The position field preserves the order of first appearance in the text.
    """

    post = models.ForeignKey(
        "engine.Post",
        on_delete=models.CASCADE,
        related_name="citations",
    )
    source = models.ForeignKey(
        "engine.Source",
        on_delete=models.CASCADE,
        related_name="post_citations",
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Order of first appearance in the post content.",
    )
    annotation = models.TextField(
        blank=True,
        help_text="Optional per-post note about this source (for annotated bibliographies).",
    )

    class Meta:
        unique_together = [("post", "source")]
        ordering = ["position"]
        indexes = [
            models.Index(fields=["post", "position"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self):
        return f"{self.post} cites {self.source}"


class PostFurtherReading(TimeStampedModel):
    """
    A curated "Further Reading" entry on a post.

    Unlike PostCitation (derived from [@key] references in content), these
    are hand-picked recommendations, edited in the post admin and rendered
    as a distinct section after the bibliography.
    """

    post = models.ForeignKey(
        "engine.Post",
        on_delete=models.CASCADE,
        related_name="further_reading",
    )
    source = models.ForeignKey(
        "engine.Source",
        on_delete=models.CASCADE,
        related_name="further_reading_entries",
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Display order within the Further Reading section.",
    )
    note = models.TextField(
        blank=True,
        help_text="Optional note shown beneath the entry (why it's recommended).",
    )

    class Meta:
        unique_together = [("post", "source")]
        ordering = ["position"]
        indexes = [models.Index(fields=["post", "position"])]

    def __str__(self):
        return f"{self.post} recommends {self.source}"
