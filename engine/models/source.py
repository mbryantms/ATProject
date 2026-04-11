"""
Source model for the bibliography system.

A centralized, universal source library. Every citable item — journal articles,
books, chapters, web pages, videos, reports, legislation, software, datasets,
interviews, and any other reference type — is stored as a single record.

Uses the CSL (Citation Style Language) type taxonomy and stores both structured
queryable fields and a canonical CSL-JSON representation for citation formatting.
"""

import logging

from django.contrib.postgres.search import SearchVectorField
from django.core.validators import RegexValidator
from django.db import models

from engine.bibliography.citation_keys import (
    CITATION_KEY_PATTERN,
    generate_citation_key,
    resolve_collision,
)

from .base import (
    SoftDeleteManager,
    SoftDeleteModel,
    SoftDeleteQuerySet,
    TimeStampedModel,
)

logger = logging.getLogger(__name__)


class SourceType(models.TextChoices):
    """CSL type taxonomy — the standard used by Zotero, Mendeley, and Pandoc."""

    ARTICLE = "article", "Article"
    ARTICLE_JOURNAL = "article-journal", "Journal Article"
    ARTICLE_MAGAZINE = "article-magazine", "Magazine Article"
    ARTICLE_NEWSPAPER = "article-newspaper", "Newspaper Article"
    BILL = "bill", "Bill"
    BOOK = "book", "Book"
    BROADCAST = "broadcast", "Broadcast"
    CHAPTER = "chapter", "Book Chapter"
    CLASSIC = "classic", "Classic"
    COLLECTION = "collection", "Collection"
    DATASET = "dataset", "Dataset"
    DOCUMENT = "document", "Document"
    ENTRY = "entry", "Entry"
    ENTRY_DICTIONARY = "entry-dictionary", "Dictionary Entry"
    ENTRY_ENCYCLOPEDIA = "entry-encyclopedia", "Encyclopedia Entry"
    EVENT = "event", "Event"
    FIGURE = "figure", "Figure"
    GRAPHIC = "graphic", "Graphic"
    HEARING = "hearing", "Hearing"
    INTERVIEW = "interview", "Interview"
    LEGAL_CASE = "legal_case", "Legal Case"
    LEGISLATION = "legislation", "Legislation"
    MANUSCRIPT = "manuscript", "Manuscript"
    MAP = "map", "Map"
    MOTION_PICTURE = "motion_picture", "Film"
    MUSICAL_SCORE = "musical_score", "Musical Score"
    PAMPHLET = "pamphlet", "Pamphlet"
    PAPER_CONFERENCE = "paper-conference", "Conference Paper"
    PATENT = "patent", "Patent"
    PERFORMANCE = "performance", "Performance"
    PERIODICAL = "periodical", "Periodical"
    PERSONAL_COMMUNICATION = "personal_communication", "Personal Communication"
    POST = "post", "Post"
    POST_WEBLOG = "post-weblog", "Blog Post"
    REGULATION = "regulation", "Regulation"
    REPORT = "report", "Report"
    REVIEW = "review", "Review"
    REVIEW_BOOK = "review-book", "Book Review"
    SOFTWARE = "software", "Software"
    SONG = "song", "Song"
    SPEECH = "speech", "Speech"
    STANDARD = "standard", "Standard"
    THESIS = "thesis", "Thesis"
    TREATY = "treaty", "Treaty"
    WEBPAGE = "webpage", "Web Page"


class UrlStatus(models.TextChoices):
    """URL health check status."""

    UNCHECKED = "unchecked", "Unchecked"
    OK = "ok", "OK"
    REDIRECT = "redirect", "Redirect"
    BROKEN = "broken", "Broken"
    ARCHIVED = "archived", "Archived"


class SourceQuerySet(SoftDeleteQuerySet):
    """Custom queryset for Source with domain-specific filters."""

    def by_type(self, source_type):
        return self.filter(source_type=source_type)

    def with_doi(self):
        return self.exclude(doi="")

    def with_url(self):
        return self.exclude(url="")

    def broken_urls(self):
        return self.filter(url_status=UrlStatus.BROKEN)

    def unchecked_urls(self):
        return self.filter(url_status=UrlStatus.UNCHECKED).exclude(url="")

    def from_zotero(self):
        return self.exclude(zotero_key="")

    def cited(self):
        """Sources that are cited in at least one post."""
        return self.filter(post_citations__isnull=False).distinct()


class SourceManager(SoftDeleteManager):
    """Manager for Source that uses SourceQuerySet."""

    def get_queryset(self):
        return SourceQuerySet(self.model, using=self._db).alive()

    def by_type(self, source_type):
        return self.get_queryset().by_type(source_type)

    def with_doi(self):
        return self.get_queryset().with_doi()

    def with_url(self):
        return self.get_queryset().with_url()

    def broken_urls(self):
        return self.get_queryset().broken_urls()

    def unchecked_urls(self):
        return self.get_queryset().unchecked_urls()

    def from_zotero(self):
        return self.get_queryset().from_zotero()

    def cited(self):
        return self.get_queryset().cited()


citation_key_validator = RegexValidator(
    regex=CITATION_KEY_PATTERN,
    message="Citation key must start with a letter or digit, and contain only "
    "lowercase letters, digits, hyphens, and underscores.",
)


class Source(TimeStampedModel, SoftDeleteModel):
    """
    A citable source in the universal source library.

    Stores both structured, queryable fields and a canonical CSL-JSON blob.
    The structured fields power admin search/filtering/display. The CSL-JSON
    is the input for the citation formatting engine (citeproc-js).
    """

    # -- Identity --
    citation_key = models.CharField(
        max_length=120,
        unique=True,
        db_index=True,
        blank=True,
        validators=[citation_key_validator],
        help_text='Unique key for citations, e.g., "smith2024climate". '
        "Auto-generated if left blank.",
    )
    source_type = models.CharField(
        max_length=40,
        choices=SourceType.choices,
        default=SourceType.WEBPAGE,
        db_index=True,
        help_text="CSL source type.",
    )
    title = models.TextField(
        help_text="Full title of the source.",
    )

    # -- People (CSL name-variable format) --
    authors = models.JSONField(
        default=list,
        blank=True,
        help_text='List of author objects: [{"family": "Smith", "given": "John"}, ...]',
    )
    editors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of editor objects in CSL name-variable format.",
    )
    translators = models.JSONField(
        default=list,
        blank=True,
        help_text="List of translator objects in CSL name-variable format.",
    )

    # -- Publication metadata --
    container_title = models.CharField(
        max_length=500,
        blank=True,
        help_text="Journal, book, or website name.",
    )
    publisher = models.CharField(max_length=300, blank=True)
    publisher_place = models.CharField(
        max_length=200,
        blank=True,
        help_text="City of publication.",
    )
    volume = models.CharField(max_length=20, blank=True)
    issue = models.CharField(max_length=20, blank=True)
    page = models.CharField(
        max_length=50,
        blank=True,
        help_text='Page range, e.g., "100-115".',
    )
    edition = models.CharField(max_length=50, blank=True)

    # -- Dates (CSL date-parts format for partial dates) --
    issued_date = models.JSONField(
        null=True,
        blank=True,
        help_text='CSL date, e.g., {"date-parts": [[2024, 3, 15]]}. '
        "Supports partial dates (year-only, year-month).",
    )
    accessed_date = models.JSONField(
        null=True,
        blank=True,
        help_text="Date the source was last accessed (for web sources).",
    )

    # -- Identifiers --
    doi = models.CharField(
        "DOI",
        max_length=200,
        blank=True,
        db_index=True,
        help_text='Digital Object Identifier, e.g., "10.1038/s41558-024-01234-5".',
    )
    isbn = models.CharField(
        "ISBN",
        max_length=20,
        blank=True,
    )
    issn = models.CharField(
        "ISSN",
        max_length=20,
        blank=True,
    )
    pmid = models.CharField(
        "PubMed ID",
        max_length=20,
        blank=True,
    )
    url = models.URLField(
        "URL",
        max_length=2000,
        blank=True,
    )

    # -- Content --
    abstract = models.TextField(blank=True)
    language = models.CharField(max_length=12, default="en", blank=True)
    note = models.TextField(
        blank=True,
        help_text="General notes about this source.",
    )

    # -- Canonical CSL-JSON (auto-synced on save) --
    csl_json = models.JSONField(
        "CSL-JSON",
        default=dict,
        blank=True,
        help_text="Canonical CSL-JSON representation. Auto-generated from structured fields.",
    )

    # -- Zotero sync tracking (Phase 4) --
    zotero_key = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Zotero item key for sync tracking.",
    )
    zotero_version = models.IntegerField(
        null=True,
        blank=True,
        help_text="Zotero library version at last sync.",
    )
    zotero_raw = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw Zotero JSON data.",
    )

    # -- URL health (Phase 7) --
    url_status = models.CharField(
        max_length=20,
        choices=UrlStatus.choices,
        default=UrlStatus.UNCHECKED,
        db_index=True,
    )
    url_last_checked = models.DateTimeField(null=True, blank=True)
    url_check_count = models.PositiveIntegerField(default=0)
    url_archive = models.URLField(
        max_length=2000,
        blank=True,
        help_text="Wayback Machine or other archive URL.",
    )

    # -- File storage (Phase 6) --
    archived_file = models.FileField(
        upload_to="sources/%Y/%m/",
        blank=True,
        help_text="Archived copy of the source (PDF, HTML, EPUB).",
    )
    archived_file_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hash for deduplication.",
    )

    # -- Search --
    search_vector = SearchVectorField(null=True, blank=True)

    # -- Managers --
    objects = SourceManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source_type", "is_deleted"]),
            models.Index(fields=["url_status", "url_last_checked"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(citation_key__regex=r"^[a-z0-9][a-z0-9_-]*$"),
                name="valid_citation_key_format",
            ),
        ]

    def __str__(self):
        return f"{self.citation_key}: {self.title[:80]}"

    def _generate_citation_key(self):
        """Auto-generate a citation key from author + year + title."""
        base_key = generate_citation_key(
            authors=self.authors or [],
            issued_date=self.issued_date,
            title=self.title or "",
        )
        # Collect existing keys (including soft-deleted) for collision check
        existing_keys = set(
            Source.all_objects.values_list("citation_key", flat=True)
        )
        # Exclude our own key if updating
        if self.pk:
            try:
                existing_keys.discard(
                    Source.all_objects.get(pk=self.pk).citation_key
                )
            except Source.DoesNotExist:
                pass
        return resolve_collision(base_key, existing_keys)

    def clean(self):
        """Auto-generate citation key and CSL-JSON before validation."""
        super().clean()

        if not self.citation_key:
            self.citation_key = self._generate_citation_key()

        self.csl_json = self._build_csl_json()

    def save(self, *args, **kwargs):
        # Safety fallback for programmatic use that skips clean()
        if not self.citation_key:
            self.citation_key = self._generate_citation_key()

        # Auto-rebuild CSL-JSON from structured fields
        self.csl_json = self._build_csl_json()

        super().save(*args, **kwargs)

    def _build_csl_json(self) -> dict:
        """Build a CSL-JSON dict from structured fields."""
        csl = {
            "id": self.citation_key,
            "type": self.source_type,
            "title": self.title,
        }

        if self.authors:
            csl["author"] = self.authors
        if self.editors:
            csl["editor"] = self.editors
        if self.translators:
            csl["translator"] = self.translators

        if self.container_title:
            csl["container-title"] = self.container_title
        if self.publisher:
            csl["publisher"] = self.publisher
        if self.publisher_place:
            csl["publisher-place"] = self.publisher_place
        if self.volume:
            csl["volume"] = self.volume
        if self.issue:
            csl["issue"] = self.issue
        if self.page:
            csl["page"] = self.page
        if self.edition:
            csl["edition"] = self.edition

        if self.issued_date:
            csl["issued"] = self.issued_date
        if self.accessed_date:
            csl["accessed"] = self.accessed_date

        if self.doi:
            csl["DOI"] = self.doi
        if self.isbn:
            csl["ISBN"] = self.isbn
        if self.issn:
            csl["ISSN"] = self.issn
        if self.pmid:
            csl["PMID"] = self.pmid
        if self.url:
            csl["URL"] = self.url

        if self.abstract:
            csl["abstract"] = self.abstract
        if self.language:
            csl["language"] = self.language
        if self.note:
            csl["note"] = self.note

        return csl

    @property
    def year(self) -> str | None:
        """Extract the year from issued_date for display."""
        if self.issued_date:
            date_parts = self.issued_date.get("date-parts", [[]])
            if date_parts and date_parts[0]:
                return str(date_parts[0][0])
        return None

    @property
    def first_author(self) -> str:
        """Extract the first author's name for display."""
        if not self.authors:
            return ""
        first = self.authors[0]
        if "family" in first:
            given = first.get("given", "")
            if given:
                return f"{first['family']}, {given[0]}."
            return first["family"]
        return first.get("literal", "")
