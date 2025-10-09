from __future__ import annotations

from typing import Any, Iterable, Mapping, TypedDict

from bs4 import BeautifulSoup, NavigableString, Tag
from django.utils.text import slugify


class HeadingNode(TypedDict):
    level: int
    id: str
    title: str
    title_html: str
    children: list["HeadingNode"]


def _extract_heading_contents(heading: Tag) -> tuple[str, str]:
    """
    Return the plain text and inner HTML that should be displayed for a heading.

    Headings rendered by our Markdown pipeline wrap the text in an anchor and
    append a copy-link button. We only want the human-facing portion for the
    TOC entry, so prefer the anchor contents when present.
    """
    anchor = heading.find("a")
    if anchor:
        # Keep any inline markup (code, emphasis, etc.) while providing a plain string.
        html = "".join(str(child) for child in anchor.contents)
        text = anchor.get_text(separator=" ", strip=True)
        return text, html

    # Fallback: collect text from all non-button children to avoid including copy buttons.
    parts: list[str] = []
    html_parts: list[str] = []
    for child in heading.contents:
        if isinstance(child, NavigableString):
            value = str(child).strip()
            if value:
                parts.append(value)
                html_parts.append(value)
            continue

        if isinstance(child, Tag) and child.name == "button":
            continue

        if isinstance(child, Tag):
            text_value = child.get_text(separator=" ", strip=True)
            if text_value:
                parts.append(text_value)
            html_parts.append(str(child))

    text = " ".join(parts).strip()
    html = "".join(html_parts).strip() or text
    return text, html


def extract_toc_from_html(html: str) -> list[HeadingNode]:
    """
    Given rendered HTML, return a hierarchical list of headings for a TOC.

    The resulting structure is a list of dictionaries. Each dictionary contains:
        - level: Heading level (1-6)
        - id: HTML id/slug for the heading
        - title: Plain-text version of the heading
        - title_html: HTML snippet preserving inline formatting
        - children: Nested list of child headings
    """
    soup = BeautifulSoup(html, "html.parser")
    toc: list[HeadingNode] = []
    stack: list[HeadingNode] = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(heading.name[1])  # "h2" -> 2
        text, html_contents = _extract_heading_contents(heading)
        if not text:
            continue

        identifier = heading.get("id") or slugify(text)

        node: HeadingNode = {
            "level": level,
            "id": identifier,
            "title": text,
            "title_html": html_contents,
            "children": [],
        }

        while stack and stack[-1]["level"] >= level:
            stack.pop()

        if stack:
            stack[-1]["children"].append(node)
        else:
            toc.append(node)

        stack.append(node)

    # Ensure footnotes appear in the TOC if present in the document even without an explicit heading.
    footnotes_section = soup.find(id="footnotes")

    def contains_id(nodes: list[HeadingNode], target: str) -> bool:
        for node in nodes:
            if node["id"] == target:
                return True
            if contains_id(node.get("children", []), target):
                return True
        return False

    if footnotes_section and not contains_id(toc, "footnotes"):
            toc.append(
                {
                    "level": 1,
                    "id": "footnotes",
                    "title": "Footnotes",
                    "title_html": "Footnotes",
                    "children": [],
                }
            )

    return toc


def _prepare_heading_node(raw: Mapping[str, Any]) -> HeadingNode | None:
    """Coerce arbitrary mapping data into a HeadingNode structure."""
    level_value = raw.get("level")
    try:
        level = int(level_value)
    except (TypeError, ValueError):
        level = 1
    level = max(1, min(level, 6))

    identifier = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    title_html = str(raw.get("title_html") or title).strip()

    if not identifier or not (title or title_html):
        return None

    children_data = raw.get("children")
    children: list[HeadingNode] = []
    if isinstance(children_data, Iterable) and not isinstance(children_data, (str, bytes, Mapping)):
        for child in children_data:
            if isinstance(child, Mapping):
                prepared = _prepare_heading_node(child)
                if prepared:
                    children.append(prepared)

    return {
        "level": level,
        "id": identifier,
        "title": title or BeautifulSoup(title_html, "html.parser").get_text(strip=True),
        "title_html": title_html or title,
        "children": children,
    }


def normalize_toc_structure(items: Iterable[Mapping[str, Any]]) -> list[HeadingNode]:
    """
    Normalize previously stored TOC data into the hierarchical HeadingNode form.

    Older posts may have a flat list with only level/id/title entries. This helper
    rebuilds the nested structure so templates can render consistently without
    requiring every post to be re-saved.
    """
    candidates = [item for item in items if isinstance(item, Mapping)]
    if not candidates:
        return []

    has_children = any(
        isinstance(item.get("children"), Iterable)
        and not isinstance(item.get("children"), (str, bytes, Mapping))
        for item in candidates
    )

    # If at least one item already declares children, respect that structure.
    if has_children:
        normalized: list[HeadingNode] = []
        for item in candidates:
            prepared = _prepare_heading_node(item)
            if prepared:
                normalized.append(prepared)
        return normalized

    normalized_tree: list[HeadingNode] = []
    stack: list[HeadingNode] = []
    for item in candidates:
        base = dict(item)
        base.setdefault("children", [])
        prepared = _prepare_heading_node(base)
        if not prepared:
            continue

        level = prepared["level"]
        while stack and stack[-1]["level"] >= level:
            stack.pop()

        if stack:
            stack[-1]["children"].append(prepared)
        else:
            normalized_tree.append(prepared)

        stack.append(prepared)

    return normalized_tree
