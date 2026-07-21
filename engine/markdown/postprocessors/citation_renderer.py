"""
Postprocessor that resolves citation placeholders and renders bibliography.

Runs after Pandoc has converted markdown to HTML. Finds %%CITE:...%% placeholder
tokens (inserted by the citation_escaper preprocessor), resolves them against the
Source library, formats via citeproc-js, and produces inline citation HTML + a
bibliography section appended to the content.

Placeholder format (from citation_escaper):
    %%CITE:key%%                — parenthetical citation
    %%CITE:key:locator%%        — with locator (e.g., pp. 42-56)
    %%MCITE:key1;key2%%         — multi-source citation
    %%NCITE:key%%               — narrative citation
    %%SCITE:key%%               — suppress-author citation
"""

import logging
import re

from engine.bibliography.formatter import format_citations
from engine.bibliography.renderer import (
    render_bibliography_section,
    render_inline_citation,
    render_unresolved_citation,
)

logger = logging.getLogger(__name__)

# Match any citation placeholder token
_PLACEHOLDER = re.compile(r"%%([NMSC]?CITE):(.+?)%%")


def citation_renderer(html: str, context: dict) -> str:
    """
    Resolve citation placeholders and render bibliography.

    Writes resolved citation data to context["resolved_citations"] for
    the Celery task to sync PostCitation records.
    """
    # Quick check: any placeholders at all?
    if (
        "%%CITE:" not in html
        and "%%NCITE:" not in html
        and "%%MCITE:" not in html
        and "%%SCITE:" not in html
    ):
        # No citations — signal the task to clean up any stale PostCitation records
        context["resolved_citations"] = []
        return html

    # 1. Collect all placeholders and extract unique keys
    placeholders = list(_PLACEHOLDER.finditer(html))
    if not placeholders:
        context["resolved_citations"] = []
        return html

    citation_clusters = []
    all_keys = []
    seen_keys = set()

    for match in placeholders:
        cluster_type = match.group(1)  # CITE, NCITE, MCITE, SCITE
        content = match.group(2)

        cluster_keys, cluster_items = _parse_placeholder(cluster_type, content)

        for key in cluster_keys:
            if key not in seen_keys:
                seen_keys.add(key)
                all_keys.append(key)

        citation_clusters.append(
            {
                "type": cluster_type,
                "content": content,
                "keys": cluster_keys,
                "items": cluster_items,
                "match": match,
            }
        )

    if not all_keys:
        return html

    # 2. Batch-resolve all keys against the database
    from engine.models import Source

    sources = {
        s.citation_key: s for s in Source.objects.filter(citation_key__in=all_keys)
    }

    # 3. Build citeproc input from resolved sources
    resolved_keys = [k for k in all_keys if k in sources]
    unresolved_keys = [k for k in all_keys if k not in sources]

    if unresolved_keys:
        logger.warning("Unresolved citation keys: %s", unresolved_keys)

    # Build CSL-JSON items for citeproc (archive URL swapped in when the
    # primary URL is known-broken)
    csl_items = [_csl_item(sources[key]) for key in resolved_keys]

    # Build citation clusters for citeproc (in document order)
    citeproc_clusters = []
    for cluster in citation_clusters:
        cite_items = []
        for item in cluster["items"]:
            if item["key"] in sources:
                ci = {"id": item["key"]}
                if item.get("locator"):
                    ci["locator"] = item["locator"]
                    ci["label"] = item.get("label", "page")
                if item.get("suppress_author"):
                    ci["suppress-author"] = True
                cite_items.append(ci)

        if cite_items:
            citeproc_clusters.append(
                {
                    "citationItems": cite_items,
                    "properties": {"noteIndex": 0},
                }
            )

    # 4. Determine citation style: post override > site default > "apa"
    style = "apa"
    post = context.get("post")
    if post and getattr(post, "citation_style", ""):
        style = post.citation_style
    else:
        try:
            from engine.models import SiteSettings

            style = SiteSettings.load().default_citation_style or "apa"
        except Exception:
            pass

    # 5. Format via citeproc-js
    formatted = format_citations(
        items=csl_items,
        citation_clusters=citeproc_clusters,
        style=style,
    )

    # 5. Replace placeholders with formatted inline citations
    # Map citeproc cluster index to our citation_clusters
    citeproc_idx = 0
    result_parts = []
    last_end = 0

    for cluster in citation_clusters:
        match = cluster["match"]
        result_parts.append(html[last_end : match.start()])

        # Check if any keys in this cluster resolved
        resolved_in_cluster = [k for k in cluster["keys"] if k in sources]

        if not resolved_in_cluster:
            # All keys unresolved — render as unresolved
            unresolved_html = " ".join(
                render_unresolved_citation(k) for k in cluster["keys"]
            )
            result_parts.append(unresolved_html)
        elif citeproc_idx < len(formatted.citations):
            # Use citeproc formatted output
            citation_text = formatted.citations[citeproc_idx]
            is_narrative = cluster["type"] == "NCITE"
            result_parts.append(
                render_inline_citation(
                    citation_text=citation_text,
                    citation_keys=resolved_in_cluster,
                    is_narrative=is_narrative,
                )
            )
            citeproc_idx += 1
        else:
            # Fallback: shouldn't happen, but handle gracefully
            result_parts.append(
                render_inline_citation(
                    citation_text=f"({', '.join(resolved_in_cluster)})",
                    citation_keys=resolved_in_cluster,
                    is_narrative=cluster["type"] == "NCITE",
                )
            )

        last_end = match.end()

    result_parts.append(html[last_end:])
    html = "".join(result_parts)

    # 6. Append bibliography section
    if formatted.bibliography:
        source_files = _public_file_urls(sources, resolved_keys)

        bib_html = render_bibliography_section(
            formatted.bibliography,
            source_files=source_files,
            citation_format=formatted.citation_format,
            annotations=_post_annotations(context.get("post"), resolved_keys),
        )
        # Insert before footnotes section if present, otherwise append
        footnotes_marker = '<section id="footnotes"'
        footnotes_alt = '<section class="footnotes"'

        if footnotes_marker in html:
            html = html.replace(footnotes_marker, bib_html + "\n" + footnotes_marker)
        elif footnotes_alt in html:
            html = html.replace(footnotes_alt, bib_html + "\n" + footnotes_alt)
        else:
            html = html + "\n" + bib_html

    # 7. Write resolved citation data to context for PostCitation sync
    resolved_citations = []
    for position, key in enumerate(resolved_keys):
        resolved_citations.append({"key": key, "position": position})

    context["resolved_citations"] = resolved_citations

    return html


def _public_file_urls(sources: dict, resolved_keys: list[str]) -> dict[str, list[str]]:
    """
    Map citation_key -> ordered URLs of public archived files, for the
    type-labeled file links in the bibliography. One batched query; PDFs
    sort first so the most readable format leads.
    """
    if not resolved_keys:
        return {}
    from engine.models import SourceFile

    pk_to_key = {sources[key].pk: key for key in resolved_keys}
    grouped: dict[int, list] = {}
    for source_file in SourceFile.objects.filter(
        source_id__in=pk_to_key, is_public=True
    ).exclude(file=""):
        grouped.setdefault(source_file.source_id, []).append(source_file)

    source_files: dict[str, list[str]] = {}
    for source_id, files in grouped.items():
        files.sort(key=lambda f: (f.kind != "pdf", f.created_at))
        urls = []
        for source_file in files:
            try:
                urls.append(source_file.file.url)
            except ValueError:
                pass
        if urls:
            source_files[pk_to_key[source_id]] = urls
    return source_files


def _csl_item(source) -> dict:
    """
    Return the source's CSL-JSON for formatting, preferring the archive URL
    when the primary URL is known-broken (link-rot remediation).
    """
    if source.url_archive and source.url_status in ("broken", "archived"):
        item = dict(source.csl_json)
        item["URL"] = source.url_archive
        return item
    return source.csl_json


def _post_annotations(post, keys: list[str]) -> dict[str, str]:
    """
    Map citation_key -> per-post annotation for annotated bibliographies.

    Annotations live on PostCitation rows (edited via the post admin inline);
    unsaved posts (previews) have none.
    """
    if not post or not getattr(post, "pk", None):
        return {}
    from engine.models import PostCitation

    return {
        pc.source.citation_key: pc.annotation
        for pc in PostCitation.objects.filter(post=post, source__citation_key__in=keys)
        .exclude(annotation="")
        .select_related("source")
    }


def _parse_placeholder(cluster_type: str, content: str) -> tuple[list[str], list[dict]]:
    """
    Parse a placeholder's content into keys and items.

    Returns:
        Tuple of (keys_list, items_list) where items have key, locator, label, suppress_author.
    """
    keys = []
    items = []

    if cluster_type == "MCITE":
        # Multi-citation: key1;key2 or key1:locator;key2
        for part in content.split(";"):
            part = part.strip()
            suppress = part.startswith("S")
            if suppress:
                part = part[1:]

            if ":" in part:
                key, locator = part.split(":", 1)
                locator, label = _parse_locator_from_placeholder(locator)
            else:
                key = part
                locator = ""
                label = "page"

            keys.append(key)
            items.append(
                {
                    "key": key,
                    "locator": locator,
                    "label": label,
                    "suppress_author": suppress,
                }
            )

    elif cluster_type in ("CITE", "SCITE"):
        # Single citation, possibly with locator
        suppress = cluster_type == "SCITE"

        if ":" in content:
            key, locator = content.split(":", 1)
            locator, label = _parse_locator_from_placeholder(locator)
        else:
            key = content
            locator = ""
            label = "page"

        keys.append(key)
        items.append(
            {
                "key": key,
                "locator": locator,
                "label": label,
                "suppress_author": suppress,
            }
        )

    elif cluster_type == "NCITE":
        # Narrative citation (no locator support in bare @key)
        keys.append(content)
        items.append(
            {
                "key": content,
                "locator": "",
                "label": "page",
                "suppress_author": False,
            }
        )

    return keys, items


def _parse_locator_from_placeholder(locator_text: str) -> tuple[str, str]:
    """Parse a locator from placeholder format back into (value, label)."""
    locator_text = locator_text.strip()

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
        "vol.": "volume",
        "fig.": "figure",
        "no.": "issue",
        "l.": "line",
        "n.": "note",
    }

    for prefix, label in prefixes.items():
        if locator_text.lower().startswith(prefix):
            value = locator_text[len(prefix) :].strip()
            return value, label

    return locator_text, "page"


def citation_renderer_default(html: str, context: dict) -> str:
    """
    Default configuration for citation_renderer.

    Register this in POSTPROCESSORS.
    """
    return citation_renderer(html, context)
