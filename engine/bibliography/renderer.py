"""
Bibliography HTML renderer.

Generates inline citation HTML elements and the bibliography section
from formatted citation data (produced by the formatter/citeproc-js).
"""

import html
import re

# Compact link icon SVG (same as the heading copy-section-link-button)
_LINK_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512">'
    '<path d="M0 256C0 167.6 71.63 96 160 96H256C273.7 96 288 110.3 '
    "288 128C288 145.7 273.7 160 256 160H160C106.1 160 64 202.1 64 "
    "256C64 309 106.1 352 160 352H256C273.7 352 288 366.3 288 384C288 "
    "401.7 273.7 416 256 416H160C71.63 416 0 344.4 0 256zM480 416H384"
    "C366.3 416 352 401.7 352 384C352 366.3 366.3 352 384 352H480C533 "
    "352 576 309 576 256C576 202.1 533 160 480 160H384C366.3 160 352 "
    "145.7 352 128C352 110.3 366.3 96 384 96H480C568.4 96 640 167.6 "
    "640 256C640 344.4 568.4 416 480 416zM416 224C433.7 224 448 238.3 "
    "448 256C448 273.7 433.7 288 416 288H224C206.3 288 192 273.7 192 "
    '256C192 238.3 206.3 224 224 224H416z"></path>'
    "</svg>"
)


def render_inline_citation(
    citation_text: str,
    citation_keys: list[str],
    is_narrative: bool = False,
) -> str:
    """
    Render an inline citation as an HTML anchor element.

    Args:
        citation_text: Formatted citation text from citeproc (e.g., "(Smith, 2024)").
        citation_keys: List of citation keys in this cluster (for linking).
        is_narrative: Whether this is a narrative citation (no brackets).

    Returns:
        HTML string for the inline citation.
    """
    # Link to the first source's bibliography entry
    first_key = citation_keys[0] if citation_keys else ""
    href = f"#ref-{first_key}"

    # Store all keys as data attribute for tooltip
    keys_attr = html.escape(" ".join(citation_keys))

    # Escape the citation text for use in data attribute
    escaped_text = html.escape(citation_text)

    css_class = "citation citation-narrative" if is_narrative else "citation"

    return (
        f'<a href="{href}" class="{css_class}" '
        f'role="doc-noteref" '
        f'data-citation-keys="{keys_attr}" '
        f'data-citation="{escaped_text}">'
        f"{citation_text}</a>"
    )


def render_unresolved_citation(key: str) -> str:
    """Render a visibly unresolved citation reference."""
    return f'<span class="citation-unresolved">[??{html.escape(key)}]</span>'


_CSL_LEFT_MARGIN_RE = re.compile(
    r'<div class="csl-left-margin">(.*?)</div>\s*', re.DOTALL
)


def _extract_csl_number(formatted_html: str) -> tuple[str | None, str]:
    """
    Extract the citeproc-generated number from a numeric-style bibliography entry.

    Citeproc renders numeric styles with ``second-field-align="flush"`` as::

        <div class="csl-entry">
          <div class="csl-left-margin">[1]</div>
          <div class="csl-right-inline">Author, ...</div>
        </div>

    Returns:
        ``(number_text, cleaned_html)`` where *number_text* is the content of
        ``csl-left-margin`` (e.g. ``"[1]"``) and *cleaned_html* has that div
        removed.  If no left-margin div is found, returns ``(None, original)``.
    """
    m = _CSL_LEFT_MARGIN_RE.search(formatted_html)
    if not m:
        return None, formatted_html
    number_text = m.group(1).strip()
    cleaned = formatted_html[: m.start()] + formatted_html[m.end() :]
    return number_text, cleaned


def render_bibliography_section(
    entries: list[tuple[str, str]],
    source_files: dict[str, str] | None = None,
    citation_format: str = "author-date",
) -> str:
    """
    Render the bibliography section HTML.

    Args:
        entries: List of (citation_key, formatted_html) tuples, already sorted
            by the citation formatter according to the active style.
        source_files: Optional dict mapping citation_key -> file URL for [PDF] links.
        citation_format: CSL citation-format category (``"numeric"``,
            ``"author-date"``, ``"author"``, or ``"note"``).

    Returns:
        Complete HTML for the bibliography section, or empty string if no entries.
    """
    if not entries:
        return ""

    source_files = source_files or {}
    is_numeric = citation_format == "numeric"

    items_html = []
    for idx, (key, formatted_html) in enumerate(entries, start=1):
        escaped_key = html.escape(key)

        # Build the number/anchor element with link icon for copy affordance
        link_icon = (
            f'<span class="reference-link-icon" aria-hidden="true">'
            f"{_LINK_ICON_SVG}</span>"
        )

        if is_numeric:
            number_text, formatted_html = _extract_csl_number(formatted_html)
            if not number_text:
                number_text = f"[{idx}]"
            anchor = (
                f'<a href="#ref-{escaped_key}" class="reference-anchor reference-number" '
                f'title="Link to reference {idx}">{link_icon}'
                f"{html.escape(number_text)}</a>"
            )
        else:
            anchor = (
                f'<a href="#ref-{escaped_key}" class="reference-anchor reference-ordinal" '
                f'title="Link to reference {idx}">{link_icon}'
                f'<span class="reference-ordinal-number">{idx}.</span></a>'
            )

        file_link = ""
        if key in source_files:
            file_url = html.escape(source_files[key])
            file_link = (
                f' <a href="{file_url}" class="reference-file-link" '
                f'target="_blank" rel="noopener">[PDF]</a>'
            )
        items_html.append(
            f'  <li id="ref-{escaped_key}" class="reference-entry">\n'
            f"    {anchor}\n"
            f'    <span class="reference-text">{formatted_html}</span>{file_link}\n'
            f"  </li>"
        )

    items = "\n".join(items_html)

    # Use h1.heading with self-link to match backlinks/similar posts sections
    heading = (
        '<h1 class="heading">'
        '<a href="#references" title="Link to section: § \'References\'">'
        "References"
        "</a>"
        '<button type="button" class="copy-section-link-button" '
        'title="Copy section link to clipboard" tabindex="-1">'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512">'
        '<path d="M0 256C0 167.6 71.63 96 160 96H256C273.7 96 288 110.3 '
        "288 128C288 145.7 273.7 160 256 160H160C106.1 160 64 202.1 64 "
        "256C64 309 106.1 352 160 352H256C273.7 352 288 366.3 288 384C288 "
        "401.7 273.7 416 256 416H160C71.63 416 0 344.4 0 256zM480 416H384"
        "C366.3 416 352 401.7 352 384C352 366.3 366.3 352 384 352H480C533 "
        "352 576 309 576 256C576 202.1 533 160 480 160H384C366.3 160 352 "
        "145.7 352 128C352 110.3 366.3 96 384 96H480C568.4 96 640 167.6 "
        "640 256C640 344.4 568.4 416 480 416zM416 224C433.7 224 448 238.3 "
        "448 256C448 273.7 433.7 288 416 288H224C206.3 288 192 273.7 192 "
        '256C192 238.3 206.3 224 224 224H416z"></path>'
        "</svg>"
        "</button>"
        "</h1>"
    )

    return (
        f'<section id="references" class="references level1 block" role="doc-bibliography">\n'
        f"{heading}\n"
        f'<ol class="reference-list" data-citation-format="{html.escape(citation_format)}">\n'
        f"{items}\n"
        f"</ol>\n"
        f"</section>"
    )
