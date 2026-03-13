"""
Query parser for search.

Parses raw query strings into structured components:
- Field-scoped prefixes: title:django, tag:python, author:name, category:tutorials, series:name
- Quoted phrases preserved: "machine learning"
- Negation: -javascript
- Remaining bare terms for full-text search
"""

import re
from dataclasses import dataclass, field


@dataclass
class ParsedQuery:
    fulltext_terms: list[str] = field(default_factory=list)
    title_filters: list[str] = field(default_factory=list)
    tag_filters: list[str] = field(default_factory=list)
    category_filters: list[str] = field(default_factory=list)
    series_filters: list[str] = field(default_factory=list)
    author_filters: list[str] = field(default_factory=list)
    negated_terms: list[str] = field(default_factory=list)

    @property
    def fulltext_query(self) -> str:
        """Build the full-text query string for PostgreSQL websearch."""
        parts = list(self.fulltext_terms)
        for term in self.negated_terms:
            parts.append(f"-{term}")
        return " ".join(parts)

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.fulltext_terms,
                self.title_filters,
                self.tag_filters,
                self.category_filters,
                self.series_filters,
                self.author_filters,
                self.negated_terms,
            ]
        )


# Pattern to match field:value or field:"quoted value"
FIELD_PATTERN = re.compile(
    r"(?P<field>title|tag|author|category|series):"
    r'(?:"(?P<quoted>[^"]+)"|(?P<bare>\S+))'
)

# Pattern to match standalone quoted phrases
QUOTE_PATTERN = re.compile(r'"([^"]+)"')


def parse_query(raw_query: str) -> ParsedQuery:
    """Parse a raw search query string into structured components."""
    if not raw_query or not raw_query.strip():
        return ParsedQuery()

    parsed = ParsedQuery()
    remaining = raw_query.strip()

    # Extract field-scoped filters
    for match in FIELD_PATTERN.finditer(remaining):
        field_name = match.group("field")
        value = match.group("quoted") or match.group("bare")

        if field_name == "title":
            parsed.title_filters.append(value)
        elif field_name == "tag":
            parsed.tag_filters.append(value)
        elif field_name == "category":
            parsed.category_filters.append(value)
        elif field_name == "series":
            parsed.series_filters.append(value)
        elif field_name == "author":
            parsed.author_filters.append(value)

    # Remove field-scoped filters from remaining text
    remaining = FIELD_PATTERN.sub("", remaining).strip()

    # Extract quoted phrases (keep them quoted for websearch)
    for match in QUOTE_PATTERN.finditer(remaining):
        parsed.fulltext_terms.append(f'"{match.group(1)}"')

    remaining = QUOTE_PATTERN.sub("", remaining).strip()

    # Process remaining bare terms
    for token in remaining.split():
        if not token:
            continue
        if token.startswith("-") and len(token) > 1:
            parsed.negated_terms.append(token[1:])
        else:
            parsed.fulltext_terms.append(token)

    return parsed


def resolve_tag_aliases(tag_names: list[str]) -> list[str]:
    """Resolve tag aliases to canonical tag slugs, expanding synonyms."""
    from engine.models import Tag, TagAlias

    slugs = set()
    for name in tag_names:
        # Try direct tag match
        tag = Tag.objects.active().filter(name__iexact=name).first()
        if tag:
            slugs.add(tag.slug)
            continue

        # Try alias match
        alias = (
            TagAlias.objects.select_related("tag").filter(alias__iexact=name).first()
        )
        if alias:
            slugs.add(alias.tag.slug)
            continue

        # Try slug match
        tag = Tag.objects.active().filter(slug__iexact=name).first()
        if tag:
            slugs.add(tag.slug)

    return list(slugs)
