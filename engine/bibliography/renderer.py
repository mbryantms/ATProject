"""
Bibliography HTML renderer.

Generates inline citation HTML elements and the bibliography section
from formatted citation data (produced by the formatter/citeproc-js).
"""

import html


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


def render_bibliography_section(
    entries: list[tuple[str, str]],
    source_files: dict[str, str] | None = None,
) -> str:
    """
    Render the bibliography section HTML.

    Args:
        entries: List of (citation_key, formatted_html) tuples, already sorted
            by the citation formatter according to the active style.
        source_files: Optional dict mapping citation_key -> file URL for [PDF] links.

    Returns:
        Complete HTML for the bibliography section, or empty string if no entries.
    """
    if not entries:
        return ""

    source_files = source_files or {}

    items_html = []
    for key, formatted_html in entries:
        escaped_key = html.escape(key)
        file_link = ""
        if key in source_files:
            file_url = html.escape(source_files[key])
            file_link = (
                f' <a href="{file_url}" class="reference-file-link" '
                f'target="_blank" rel="noopener">[PDF]</a>'
            )
        items_html.append(
            f'  <li id="ref-{escaped_key}" class="reference-entry">\n'
            f'    <span class="reference-text">{formatted_html}</span>{file_link}\n'
            f"  </li>"
        )

    items = "\n".join(items_html)

    return (
        f'<section id="references" class="references block" role="doc-bibliography">\n'
        f"<h2>References</h2>\n"
        f'<ol class="reference-list">\n'
        f"{items}\n"
        f"</ol>\n"
        f"</section>"
    )
