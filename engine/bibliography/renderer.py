"""
Bibliography HTML renderer.

Generates inline citation HTML elements and the bibliography section
from formatted citation data (produced by the formatter/citeproc-js).
"""

import html
import re

# Citation HTML (inline clusters and bibliography entries) is produced by the
# formatter *after* the markdown pipeline's nh3 pass (sanitize_html is the first
# postprocessor; citation_renderer runs much later), so it never passes through
# the site sanitizer. citeproc-js escapes field values, but the plain-text
# fallback path and any future formatter change would not — so we sanitize the
# citeproc/fallback output here against a tight allowlist of the presentational
# tags a CSL processor legitimately emits. This is the last line of defense for
# a stored-XSS vector whose field data comes from admin input, Zotero sync, and
# DOI/URL resolvers.
_CSL_ALLOWED_TAGS = {"i", "b", "em", "strong", "span", "sup", "sub", "div", "a"}
_CSL_ALLOWED_ATTRIBUTES = {
    "*": {"class"},
    "a": {"href", "class"},
    "div": {"class"},
    "span": {"class"},
}
_CSL_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_citation_html(fragment: str) -> str:
    """Strip anything but CSL presentational markup from a citation fragment."""
    if not fragment:
        return fragment
    import nh3

    return nh3.clean(
        fragment,
        tags=_CSL_ALLOWED_TAGS,
        attributes=_CSL_ALLOWED_ATTRIBUTES,
        url_schemes=_CSL_ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )


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

    # citation_text is rendered as visible markup; sanitize it (the data-
    # attribute copy is already html.escape'd above).
    safe_text = sanitize_citation_html(citation_text)

    return (
        f'<a href="{href}" class="{css_class}" '
        f'role="doc-noteref" '
        f'data-citation-keys="{keys_attr}" '
        f'data-citation="{escaped_text}">'
        f"{safe_text}</a>"
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


# Copy-to-clipboard button appended to every reference entry. Handled by
# static/js/citation-tooltip.js; copies the entry's .reference-text content.
_COPY_BUTTON = (
    '<button type="button" class="copy-citation-button" '
    'title="Copy reference" aria-label="Copy reference to clipboard" '
    'tabindex="-1">'
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" aria-hidden="true">'
    '<path d="M280 64h40c35.3 0 64 28.7 64 64V448c0 35.3-28.7 64-64 64H64'
    "c-35.3 0-64-28.7-64-64V128C0 92.7 28.7 64 64 64h40 9.6C121 27.5 153.3 "
    "0 192 0s71 27.5 78.4 64H280zM64 112c-8.8 0-16 7.2-16 16V448c0 8.8 7.2 "
    "16 16 16H320c8.8 0 16-7.2 16-16V128c0-8.8-7.2-16-16-16H304v24c0 13.3-"
    "10.7 24-24 24H192 104c-13.3 0-24-10.7-24-24V112H64zm128-8a24 24 0 1 0 "
    '0-48 24 24 0 1 0 0 48z"></path></svg></button>'
)


# Label shown on the archived-file link, keyed by file extension.
_FILE_LINK_LABELS = {
    "pdf": "PDF",
    "doc": "DOC",
    "docx": "DOC",
    "html": "HTML",
    "htm": "HTML",
    "epub": "EPUB",
}


def _file_link_label(file_url: str) -> str:
    """Derive the bracket label for an archived-file link from its extension."""
    path = file_url.split("?")[0].split("#")[0]
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return _FILE_LINK_LABELS.get(ext, "FILE")


def render_bibliography_section(
    entries: list[tuple[str, str]],
    source_files: dict[str, list[str]] | None = None,
    citation_format: str = "author-date",
    annotations: dict[str, str] | None = None,
) -> str:
    """
    Render the bibliography section HTML.

    Args:
        entries: List of (citation_key, formatted_html) tuples, already sorted
            by the citation formatter according to the active style.
        source_files: Optional dict mapping citation_key -> list of file URLs
            for archived-file links, each labeled by type ([PDF], [DOC], ...).
        citation_format: CSL citation-format category (``"numeric"``,
            ``"author-date"``, ``"author"``, or ``"note"``).
        annotations: Optional dict mapping citation_key -> per-post annotation
            text, rendered below the formatted reference.

    Returns:
        Complete HTML for the bibliography section, or empty string if no entries.
    """
    if not entries:
        return ""

    source_files = source_files or {}
    annotations = annotations or {}
    is_numeric = citation_format == "numeric"

    items_html = []
    for idx, (key, formatted_html) in enumerate(entries, start=1):
        escaped_key = html.escape(key)
        # Neutralize any active markup from the formatter (see
        # sanitize_citation_html) before it is embedded and cached.
        formatted_html = sanitize_citation_html(formatted_html)

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
        for raw_url in source_files.get(key, []):
            file_url = html.escape(raw_url)
            label = _file_link_label(raw_url)
            file_link += (
                f' <a href="{file_url}" class="reference-file-link" '
                f'target="_blank" rel="noopener">[{label}]</a>'
            )
        annotation_html = ""
        if key in annotations:
            annotation_html = (
                f'\n    <div class="reference-annotation">'
                f"{html.escape(annotations[key])}</div>"
            )
        items_html.append(
            f'  <li id="ref-{escaped_key}" class="reference-entry">\n'
            f"    {anchor}\n"
            f'    <span class="reference-text">{formatted_html}</span>{file_link}'
            f" {_COPY_BUTTON}"
            f"{annotation_html}\n"
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


def _format_source_entry(source) -> str:
    """
    Plain author-date rendering of a source for hand-built sections
    (Further Reading). Deliberately simple — this is a curated reading
    list, not a formal bibliography, so no citeproc round-trip.
    """
    parts = []
    author = source.first_author
    year = source.year
    if author:
        lead = html.escape(author)
        if year:
            lead += f" ({html.escape(year)})"
        parts.append(lead + ".")
    elif year:
        parts.append(f"({html.escape(year)}).")

    title = html.escape(source.title)
    link_url = source.url
    if source.url_archive and source.url_status in ("broken", "archived"):
        link_url = source.url_archive
    if link_url:
        parts.append(
            f'<a href="{html.escape(link_url)}" rel="noopener"><em>{title}</em></a>.'
        )
    else:
        parts.append(f"<em>{title}</em>.")

    if source.container_title:
        parts.append(html.escape(source.container_title) + ".")
    return " ".join(parts)


def render_further_reading_section(
    entries,
    source_files: dict[str, list[str]] | None = None,
) -> str:
    """
    Render the curated Further Reading section.

    Args:
        entries: Iterable of PostFurtherReading rows (with .source and .note),
            already ordered by position.
        source_files: Optional dict mapping citation_key -> list of public
            file URLs, as produced for the bibliography.

    Returns:
        Section HTML, or empty string when there are no entries.
    """
    entries = list(entries)
    if not entries:
        return ""
    source_files = source_files or {}

    items_html = []
    for entry in entries:
        source = entry.source
        escaped_key = html.escape(source.citation_key)

        file_link = ""
        for raw_url in source_files.get(source.citation_key, []):
            file_url = html.escape(raw_url)
            label = _file_link_label(raw_url)
            file_link += (
                f' <a href="{file_url}" class="reference-file-link" '
                f'target="_blank" rel="noopener">[{label}]</a>'
            )

        note_html = ""
        if entry.note:
            note_html = (
                f'\n    <div class="reference-annotation">'
                f"{html.escape(entry.note)}</div>"
            )

        items_html.append(
            f'  <li id="fr-{escaped_key}" class="reference-entry further-reading-entry">\n'
            f'    <span class="reference-text">{_format_source_entry(source)}</span>'
            f"{file_link}{note_html}\n"
            f"  </li>"
        )

    items = "\n".join(items_html)
    heading = (
        '<h1 class="heading">'
        '<a href="#further-reading" title="Link to section: § \'Further Reading\'">'
        "Further Reading"
        "</a>"
        "</h1>"
    )
    return (
        f'<section id="further-reading" class="further-reading level1 block">\n'
        f"{heading}\n"
        f'<ul class="reference-list" data-citation-format="author-date">\n'
        f"{items}\n"
        f"</ul>\n"
        f"</section>"
    )
