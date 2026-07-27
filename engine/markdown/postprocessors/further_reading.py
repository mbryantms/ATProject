"""
Postprocessor that renders the curated "Further Reading" section.

Unlike the bibliography (derived from [@key] citations in content), Further
Reading entries are hand-picked in the post admin (PostFurtherReading rows).
The section is inserted directly after the References section when present,
otherwise before footnotes, otherwise appended — so it renders even on posts
with no citations at all.
"""

from engine.bibliography.renderer import render_further_reading_section


def further_reading_renderer(html: str, context: dict) -> str:
    owner = context.get("content_object") or context.get("post")
    if not owner or not getattr(owner, "pk", None):
        return html

    relation = getattr(owner, "further_reading", None)
    if relation is None:
        return html
    entries = list(relation.select_related("source").order_by("position"))
    if not entries:
        return html

    from engine.markdown.postprocessors.citation_renderer import _public_file_urls

    sources = {entry.source.citation_key: entry.source for entry in entries}
    section = render_further_reading_section(
        entries,
        source_files=_public_file_urls(sources, list(sources)),
    )

    references_marker = '<section id="references"'
    if references_marker in html:
        start = html.find(references_marker)
        close = html.find("</section>", start)
        if close != -1:
            insert_at = close + len("</section>")
            return html[:insert_at] + "\n" + section + html[insert_at:]

    for marker in ('<section id="footnotes"', '<section class="footnotes"'):
        if marker in html:
            return html.replace(marker, section + "\n" + marker, 1)

    return html + "\n" + section


def further_reading_renderer_default(html: str, context: dict) -> str:
    """Default configuration for further_reading_renderer."""
    return further_reading_renderer(html, context)
