"""
Preprocessor that escapes citation syntax before Pandoc processes the markdown.

Converts Pandoc citation syntax into placeholder tokens that Pandoc passes
through as plain text. The citation_renderer postprocessor then resolves
these placeholders against the source library.

Conversions:
    [@key]              → %%CITE:key%%
    [@key, pp. 42-56]   → %%CITE:key:pp. 42-56%%
    [@key1; @key2]       → %%MCITE:key1;key2%%
    @key                 → %%NCITE:key%%
    [-@key]              → %%SCITE:key%%
"""

import re

# Bracketed citation: [@key] or [@key, locator] or [@key1; @key2; ...]
_BRACKETED = re.compile(
    r"\[("
    r"(?:-?)@[a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*(?:,\s*[^;\]]+?)?"
    r"(?:;\s*(?:-?)@[a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*(?:,\s*[^;\]]+?)?)*"
    r")\]"
)

# Narrative citation: @key not inside brackets
_NARRATIVE = re.compile(
    r"(?<![@\[\\])@([a-zA-Z0-9][a-zA-Z0-9_:.#$%&\-+?<>~/]*)"
)


def _escape_bracketed(match: re.Match) -> str:
    """Convert a bracketed citation to placeholder tokens."""
    content = match.group(1)

    # Split on ; to get individual items
    items = [item.strip() for item in content.split(";")]

    if len(items) == 1:
        # Single citation
        item = items[0]
        suppress = item.startswith("-")
        if suppress:
            item = item[1:]  # Remove -

        # Remove @ prefix
        item = item.lstrip("@")

        # Check for locator (comma-separated)
        if "," in item:
            key, locator = item.split(",", 1)
            key = key.strip()
            locator = locator.strip()
            if suppress:
                return f"%%SCITE:{key}:{locator}%%"
            return f"%%CITE:{key}:{locator}%%"

        if suppress:
            return f"%%SCITE:{item}%%"
        return f"%%CITE:{item}%%"

    # Multi-citation: extract keys and locators for each
    parts = []
    for item in items:
        item = item.strip()
        suppress = item.startswith("-")
        if suppress:
            item = item[1:]
        item = item.lstrip("@")

        if "," in item:
            key, locator = item.split(",", 1)
            key = key.strip()
            locator = locator.strip()
            prefix = "S" if suppress else ""
            parts.append(f"{prefix}{key}:{locator}")
        else:
            prefix = "S" if suppress else ""
            parts.append(f"{prefix}{item}")

    return f"%%MCITE:{';'.join(parts)}%%"


def _escape_narrative(match: re.Match) -> str:
    """Convert a narrative citation to a placeholder token."""
    key = match.group(1)
    return f"%%NCITE:{key}%%"


# Patterns for code spans and fenced code blocks that should be left untouched
_FENCED_CODE_BLOCK = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)", re.MULTILINE)
_INLINE_CODE = re.compile(r"(`+)(.+?)\1")


def escape_citations(text: str, context: dict) -> str:
    """
    Escape all citation syntax in markdown before Pandoc processing.

    The placeholders use %% delimiters which Pandoc treats as plain text.
    Citations inside inline code (`...`) and fenced code blocks are left untouched.
    """
    # Protect code spans and fenced blocks from citation processing.
    # Replace them with unique tokens, process citations, then restore.
    protected = {}
    counter = 0

    def _protect(match: re.Match) -> str:
        nonlocal counter
        token = f"%%CODEPROTECT:{counter}%%"
        protected[token] = match.group(0)
        counter += 1
        return token

    text = _FENCED_CODE_BLOCK.sub(_protect, text)
    text = _INLINE_CODE.sub(_protect, text)

    # Process bracketed citations first (they contain @ which narrative would also match)
    text = _BRACKETED.sub(_escape_bracketed, text)

    # Then process narrative citations (bare @key)
    text = _NARRATIVE.sub(_escape_narrative, text)

    # Restore protected code spans
    for token, original in protected.items():
        text = text.replace(token, original)

    return text


def citation_escaper_default(text: str, context: dict) -> str:
    """
    Default configuration for citation_escaper.

    Register this in PREPROCESSORS.
    """
    return escape_citations(text, context)
