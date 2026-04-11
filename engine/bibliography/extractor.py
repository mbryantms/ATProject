"""
Citation extraction from markdown content.

Parses Pandoc-compatible citation syntax and extracts citation keys
and their metadata (locators, suppression flags, etc.).

Supported syntax:
    [@key]                  — parenthetical citation
    [@key, pp. 42-56]       — with page locator
    [@key1; @key2]          — multiple sources in one citation
    @key                    — narrative/in-text citation
    [-@key]                 — suppress author (year only)
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Regex patterns for Pandoc citation syntax
# These operate on raw markdown, BEFORE Pandoc processing.

# A single citation item inside brackets: @key or @key, pp. 42-56
# Captures: optional suppress flag (-), key, optional locator
_CITE_ITEM = r"(-?)@([a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*)"
_CITE_LOCATOR = r"(?:,\s*(.+?))?"

# Full bracketed citation: [@key] or [@key, p. 5] or [@key1; @key2]
# The bracket contents can have multiple items separated by ;
_BRACKETED_CITATION = re.compile(
    r"\["
    r"((?:-?)@[a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*(?:,\s*[^;\]]+?)?)"
    r"(?:;\s*(?:-?)@[a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*(?:,\s*[^;\]]+?)?)*"
    r"\]"
)

# Narrative citation: @key (not inside brackets, not preceded by [- or @)
# Must be preceded by whitespace or start of line, not preceded by [ or @
_NARRATIVE_CITATION = re.compile(
    r"(?<![@\[\\])@([a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*)"
)

# Individual item within a bracketed citation (for splitting multi-cite)
_BRACKETED_ITEM = re.compile(
    r"(-?)@([a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*)(?:,\s*(.+?))?\s*$"
)


@dataclass
class CitationItem:
    """A single citation reference within a citation cluster."""

    key: str
    locator: str = ""
    label: str = "page"
    suppress_author: bool = False
    is_narrative: bool = False


@dataclass
class CitationCluster:
    """
    A group of citations that appear together in the text.

    A single [@key] is a cluster of one. [@key1; @key2] is a cluster of two.
    """

    items: list[CitationItem] = field(default_factory=list)
    original_text: str = ""
    is_narrative: bool = False


def extract_citations(markdown_text: str) -> list[CitationCluster]:
    """
    Extract all citation clusters from markdown text.

    Returns clusters in document order.
    """
    if not markdown_text:
        return []

    clusters = []
    # Track positions to maintain document order and avoid duplicates
    seen_positions: set[int] = set()

    # 1. Find bracketed citations: [@key], [@key, p. 5], [@key1; @key2]
    for match in _BRACKETED_CITATION.finditer(markdown_text):
        if match.start() in seen_positions:
            continue
        seen_positions.add(match.start())

        bracket_content = match.group(0)[1:-1]  # Strip [ and ]
        items = _parse_bracket_content(bracket_content)
        if items:
            clusters.append(
                CitationCluster(
                    items=items,
                    original_text=match.group(0),
                )
            )

    # 2. Find narrative citations: @key (not inside brackets)
    for match in _NARRATIVE_CITATION.finditer(markdown_text):
        pos = match.start()
        if pos in seen_positions:
            continue

        # Check this isn't inside a bracketed citation we already captured
        inside_bracket = False
        for bm in _BRACKETED_CITATION.finditer(markdown_text):
            if bm.start() <= pos < bm.end():
                inside_bracket = True
                break

        if inside_bracket:
            continue

        seen_positions.add(pos)
        key = match.group(1)
        clusters.append(
            CitationCluster(
                items=[CitationItem(key=key, is_narrative=True)],
                original_text=match.group(0),
                is_narrative=True,
            )
        )

    # Sort by position in document
    clusters.sort(key=lambda c: markdown_text.find(c.original_text))

    return clusters


def extract_unique_keys(clusters: list[CitationCluster]) -> list[str]:
    """Extract unique citation keys from clusters, preserving first-appearance order."""
    seen = set()
    keys = []
    for cluster in clusters:
        for item in cluster.items:
            if item.key not in seen:
                seen.add(item.key)
                keys.append(item.key)
    return keys


def _parse_bracket_content(content: str) -> list[CitationItem]:
    """Parse the content inside [...] into citation items."""
    items = []

    # Split on ; to get individual items
    parts = content.split(";")

    for part in parts:
        part = part.strip()
        match = _BRACKETED_ITEM.match(part)
        if match:
            suppress = match.group(1) == "-"
            key = match.group(2)
            locator_text = match.group(3) or ""

            locator = ""
            label = "page"
            if locator_text:
                locator, label = _parse_locator(locator_text)

            items.append(
                CitationItem(
                    key=key,
                    locator=locator,
                    label=label,
                    suppress_author=suppress,
                )
            )

    return items


def _parse_locator(text: str) -> tuple[str, str]:
    """
    Parse a locator string like "pp. 42-56" or "ch. 3" into (locator, label).

    Returns:
        Tuple of (locator_value, label_type).
    """
    text = text.strip()

    # Common locator prefixes and their CSL labels
    prefixes = {
        "p.": "page",
        "pp.": "page",
        "page": "page",
        "pages": "page",
        "ch.": "chapter",
        "chap.": "chapter",
        "chapter": "chapter",
        "sec.": "section",
        "section": "section",
        "para.": "paragraph",
        "paragraph": "paragraph",
        "vol.": "volume",
        "volume": "volume",
        "fig.": "figure",
        "figure": "figure",
        "no.": "issue",
        "l.": "line",
        "line": "line",
        "n.": "note",
        "note": "note",
    }

    for prefix, label in prefixes.items():
        if text.lower().startswith(prefix):
            locator = text[len(prefix) :].strip()
            return locator, label

    # No recognized prefix — treat entire text as page locator
    return text, "page"


def update_post_citations(post, resolved_citations: list[dict]) -> dict:
    """
    Sync PostCitation records to match the citations found in content.

    Args:
        post: Post instance.
        resolved_citations: List of dicts with "key" and "position" from rendering.

    Returns:
        Stats dict with created, deleted, unchanged counts.
    """
    from engine.models import PostCitation, Source

    if not resolved_citations:
        # No citations — delete all existing records
        deleted_count, _ = PostCitation.objects.filter(post=post).delete()
        return {"created": 0, "deleted": deleted_count, "unchanged": 0}

    # Get source objects for all cited keys
    cited_keys = [c["key"] for c in resolved_citations]
    sources_by_key = {
        s.citation_key: s for s in Source.objects.filter(citation_key__in=cited_keys)
    }

    # Build the desired state
    desired = {}
    for citation_data in resolved_citations:
        key = citation_data["key"]
        if key in sources_by_key:
            desired[sources_by_key[key].pk] = citation_data["position"]

    # Get current state
    existing = {
        pc.source_id: pc
        for pc in PostCitation.objects.filter(post=post).select_related("source")
    }

    created = 0
    deleted = 0
    unchanged = 0

    # Create new, update positions
    for source_pk, position in desired.items():
        if source_pk in existing:
            pc = existing[source_pk]
            if pc.position != position:
                pc.position = position
                pc.save(update_fields=["position", "updated_at"])
            unchanged += 1
        else:
            PostCitation.objects.create(
                post=post,
                source_id=source_pk,
                position=position,
            )
            created += 1

    # Delete citations no longer in content
    to_delete = set(existing.keys()) - set(desired.keys())
    if to_delete:
        deleted, _ = PostCitation.objects.filter(
            post=post, source_id__in=to_delete
        ).delete()

    return {"created": created, "deleted": deleted, "unchanged": unchanged}
