"""
Citation key generation and collision avoidance.

Citation keys are globally unique, human-readable identifiers used in markdown
content (e.g., [@smith2024climate]). They follow the pattern:
    {first_author_family}{year}{first_significant_title_word}

Once set and used in published content, citation keys should never change
automatically — they are the stable contract between content and data.
"""

import re
import string
import unicodedata

# Words to skip when extracting the title component of a citation key
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "not",
        "no",
        "how",
        "what",
        "when",
        "where",
        "why",
        "who",
        "which",
        "that",
        "this",
        "it",
        "its",
    }
)

# Valid citation key pattern
CITATION_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def generate_citation_key(
    authors: list[dict],
    issued_date: dict | None,
    title: str,
) -> str:
    """
    Generate a citation key from author, year, and title.

    Args:
        authors: List of CSL-JSON author dicts with "family"/"given"/"literal" keys.
        issued_date: CSL-JSON date dict, e.g., {"date-parts": [[2024, 3, 15]]}.
        title: Source title.

    Returns:
        A citation key like "smith2024climate". Does NOT check for collisions
        — use resolve_collision() to ensure uniqueness.
    """
    author_part = _extract_author_part(authors)
    year_part = _extract_year_part(issued_date)
    title_part = _extract_title_part(title)

    key = f"{author_part}{year_part}{title_part}"

    # Ensure the key is valid
    key = _normalize_key(key)

    # Ensure minimum length
    if not key:
        key = "source"

    return key


def resolve_collision(base_key: str, existing_keys: set[str]) -> str:
    """
    Resolve a citation key collision by appending a letter suffix.

    Args:
        base_key: The base citation key (e.g., "smith2024climate").
        existing_keys: Set of all existing citation keys (including soft-deleted).

    Returns:
        A unique key, e.g., "smith2024climate" if available, otherwise
        "smith2024climatea", "smith2024climateb", etc.
    """
    if base_key not in existing_keys:
        return base_key

    for suffix in string.ascii_lowercase:
        candidate = f"{base_key}{suffix}"
        if candidate not in existing_keys:
            return candidate

    # Extremely unlikely: 26 collisions exhausted, use numeric suffix
    counter = 2
    while True:
        candidate = f"{base_key}{counter}"
        if candidate not in existing_keys:
            return candidate
        counter += 1


def _extract_author_part(authors: list[dict]) -> str:
    """Extract the first author's family name, normalized for a citation key."""
    if not authors:
        return ""

    first = authors[0]
    name = first.get("family", "") or first.get("literal", "")
    if not name:
        return ""

    return _normalize_key(name)


def _extract_year_part(issued_date: dict | None) -> str:
    """Extract the year from a CSL-JSON date."""
    if not issued_date:
        return ""

    date_parts = issued_date.get("date-parts", [[]])
    if date_parts and date_parts[0]:
        return str(date_parts[0][0])

    return ""


def _extract_title_part(title: str) -> str:
    """Extract the first significant word from the title."""
    if not title:
        return ""

    # Remove punctuation and split into words
    words = re.findall(r"[a-zA-Z0-9]+", title.lower())

    # Find the first non-stop word
    for word in words:
        if word not in _STOP_WORDS and len(word) > 1:
            return _normalize_key(word)

    # If all words are stop words, use the first word
    if words:
        return _normalize_key(words[0])

    return ""


def _normalize_key(text: str) -> str:
    """
    Normalize text for use in a citation key.

    Strips accents, lowercases, removes non-alphanumeric characters.
    """
    # Decompose unicode and strip combining characters (accents)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # Lowercase and keep only alphanumeric + hyphen
    text = text.lower()
    text = re.sub(r"[^a-z0-9-]", "", text)

    # Strip leading/trailing hyphens
    text = text.strip("-")

    return text
