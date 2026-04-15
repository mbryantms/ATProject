"""
Citation formatting engine.

Calls citeproc-js via Node.js subprocess to format citations and bibliography
entries according to a specified CSL style. Falls back to simple text formatting
if the subprocess is unavailable.

This module is the single point of contact with the citation formatting engine.
Replacing the engine (e.g., switching to citeproc-py or a microservice) requires
only changing this module.
"""

import json
import logging
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths relative to this file
_BIBLIOGRAPHY_DIR = Path(__file__).parent
_BRIDGE_SCRIPT = _BIBLIOGRAPHY_DIR / "citeproc_bridge.js"
_STYLES_DIR = _BIBLIOGRAPHY_DIR / "styles"
_LOCALES_DIR = _BIBLIOGRAPHY_DIR / "locales"

# Subprocess timeout in seconds (citeproc-js is fast; 30s is generous)
_SUBPROCESS_TIMEOUT = 30

# Common short names mapped to actual CSL style filenames (without .csl)
_STYLE_ALIASES = {
    "mla": "modern-language-association",
    "chicago": "chicago-author-date",
    "chicago-notes": "chicago-notes-bibliography",
    "harvard": "harvard-cite-them-right",
}


def get_citation_format(style: str) -> str:
    """
    Return the citation-format category for a CSL style.

    Parses the ``<category citation-format="..."/>`` element from the resolved
    CSL file.  Returns one of ``"numeric"``, ``"author-date"``, ``"author"``,
    or ``"note"`` (default ``"author-date"``).
    """
    resolved = _STYLE_ALIASES.get(style.lower(), style)
    style_file = _STYLES_DIR / f"{resolved}.csl"
    if not style_file.exists():
        return "author-date"

    try:
        tree = ET.parse(style_file)  # noqa: S314
        root = tree.getroot()
        # CSL namespace
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        for cat in root.iter(f"{ns}category"):
            fmt = cat.get("citation-format")
            if fmt:
                return fmt
    except Exception:
        logger.debug("Could not parse citation-format from %s", style_file)

    return "author-date"


def _resolve_style_name(style: str) -> str:
    """Resolve a style name, checking aliases and verifying the file exists."""
    # Check alias first
    resolved = _STYLE_ALIASES.get(style.lower(), style)

    # Verify the style file exists
    style_file = _STYLES_DIR / f"{resolved}.csl"
    if style_file.exists():
        return resolved

    # Try the original name (in case alias mapping was wrong)
    if resolved != style:
        original_file = _STYLES_DIR / f"{style}.csl"
        if original_file.exists():
            return style

    logger.warning(
        "Citation style '%s' not found in %s. Falling back to 'apa'. "
        "Available styles: %s",
        style,
        _STYLES_DIR,
        ", ".join(get_available_styles()),
    )
    return "apa"


@dataclass
class FormattedOutput:
    """Result of citation formatting."""

    # Inline citation text for each citation cluster, in document order.
    # e.g., ["(Smith, 2024, p. 105)", "(Jones & Williams, 2023)"]
    citations: list[str] = field(default_factory=list)

    # Bibliography entries as (item_id, formatted_html) tuples, sorted per style.
    # e.g., [("smith2024", "<div class=\"csl-entry\">Smith, J. (2024)...</div>")]
    bibliography: list[tuple[str, str]] = field(default_factory=list)

    # Whether the output was produced by the real engine or the fallback.
    is_fallback: bool = False

    # CSL citation-format category: "numeric", "author-date", "author", or "note".
    citation_format: str = "author-date"


def format_citations(
    items: list[dict],
    citation_clusters: list[dict],
    style: str = "apa",
    lang: str = "en-US",
) -> FormattedOutput:
    """
    Format citations and bibliography using citeproc-js.

    Args:
        items: List of CSL-JSON item dicts. Each must have an "id" field
            matching the citation keys used in citation_clusters.
        citation_clusters: List of citation cluster dicts in document order.
            Each has "citationItems" (list of {"id": str, "locator": str, "label": str})
            and "properties" ({"noteIndex": int}).
        style: CSL style name (filename without .csl extension).
        lang: Language code for locale (default "en-US").

    Returns:
        FormattedOutput with inline citations and bibliography entries.
        Falls back to simple text formatting if citeproc-js is unavailable.
    """
    if not items:
        return FormattedOutput()

    # Resolve style aliases and verify file exists
    style = _resolve_style_name(style)

    # Try citeproc-js subprocess
    try:
        return _format_via_citeproc(items, citation_clusters, style, lang)
    except Exception:
        logger.exception(
            "citeproc-js subprocess failed for style=%s, %d items. "
            "Falling back to simple formatting.",
            style,
            len(items),
        )
        return _format_fallback(items, citation_clusters)


def _format_via_citeproc(
    items: list[dict],
    citation_clusters: list[dict],
    style: str,
    lang: str,
) -> FormattedOutput:
    """Call citeproc-js via Node.js subprocess."""
    request = {
        "items": items,
        "style": style,
        "citationClusters": citation_clusters,
        "stylePath": str(_STYLES_DIR),
        "localePath": str(_LOCALES_DIR),
        "lang": lang,
    }

    result = subprocess.run(
        ["node", str(_BRIDGE_SCRIPT)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "no stderr"
        raise RuntimeError(
            f"citeproc-js exited with code {result.returncode}: {stderr}"
        )

    output = json.loads(result.stdout)

    if "error" in output:
        raise RuntimeError(f"citeproc-js error: {output['error']}")

    return FormattedOutput(
        citations=output.get("citations", []),
        bibliography=[(bid, bhtml) for bid, bhtml in output.get("bibliography", [])],
        citation_format=get_citation_format(style),
    )


def _format_fallback(
    items: list[dict],
    citation_clusters: list[dict],
) -> FormattedOutput:
    """
    Simple text-based fallback when citeproc-js is unavailable.

    Produces basic [Author, Year] citations and plain-text bibliography entries.
    Not style-accurate, but ensures posts render readable content.
    """
    item_map = {item["id"]: item for item in items}

    # Build inline citations
    citations = []
    for cluster in citation_clusters:
        parts = []
        for ci in cluster.get("citationItems", []):
            item = item_map.get(ci["id"])
            if not item:
                parts.append(f"??{ci['id']}")
                continue

            author = _extract_first_author(item)
            year = _extract_year(item)
            locator = ci.get("locator", "")

            text = f"{author}, {year}" if year else author
            if locator:
                label = ci.get("label", "p.")
                text += f", {label} {locator}"
            parts.append(text)

        citations.append(f"({'; '.join(parts)})")

    # Build bibliography entries
    bibliography = []
    for item in sorted(items, key=lambda i: _extract_first_author(i).lower()):
        entry = _format_fallback_entry(item)
        bibliography.append((item["id"], entry))

    return FormattedOutput(
        citations=citations,
        bibliography=bibliography,
        is_fallback=True,
    )


def _extract_first_author(item: dict) -> str:
    """Extract first author's family name from a CSL-JSON item."""
    authors = item.get("author", [])
    if not authors:
        return item.get("title", "Unknown")[:30]
    first = authors[0]
    if "family" in first:
        return first["family"]
    if "literal" in first:
        return first["literal"]
    return "Unknown"


def _extract_year(item: dict) -> str:
    """Extract year from a CSL-JSON item's issued date."""
    issued = item.get("issued", {})
    date_parts = issued.get("date-parts", [[]])
    if date_parts and date_parts[0]:
        return str(date_parts[0][0])
    return ""


def _format_fallback_entry(item: dict) -> str:
    """Format a single bibliography entry as plain text."""
    authors = item.get("author", [])
    author_str = _format_authors_plain(authors) if authors else ""
    year = _extract_year(item)
    title = item.get("title", "")
    container = item.get("container-title", "")

    parts = []
    if author_str:
        parts.append(f"{author_str}.")
    if year:
        parts.append(f"({year}).")
    if title:
        parts.append(f"{title}.")
    if container:
        parts.append(f"<i>{container}</i>.")

    volume = item.get("volume", "")
    issue = item.get("issue", "")
    page = item.get("page", "")
    if volume:
        vol_str = f"<i>{volume}</i>"
        if issue:
            vol_str += f"({issue})"
        if page:
            vol_str += f", {page}"
        parts.append(f"{vol_str}.")

    return f'<div class="csl-entry">{" ".join(parts)}</div>'


def _format_authors_plain(authors: list[dict]) -> str:
    """Format a list of CSL-JSON authors as plain text."""
    names = []
    for a in authors:
        if "literal" in a:
            names.append(a["literal"])
        elif "family" in a:
            given = a.get("given", "")
            initials = (
                ". ".join(g[0] for g in given.split() if g) + "." if given else ""
            )
            names.append(f"{a['family']}, {initials}" if initials else a["family"])

    if len(names) == 0:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return f"{', '.join(names[:-1])}, & {names[-1]}"


def get_available_styles() -> list[str]:
    """Return list of available CSL style names (without .csl extension)."""
    if not _STYLES_DIR.exists():
        return []
    return sorted(p.stem for p in _STYLES_DIR.glob("*.csl"))
