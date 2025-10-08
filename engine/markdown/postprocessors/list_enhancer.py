# engine/markdown/postprocessors/list_enhancer.py
"""
Postprocessor that enhances list elements with classes and structure.

This postprocessor:
- Adds "list" class to all <ul> and <ol> elements
- Adds "list-level-n" class to <ul> and <ol> based on nesting depth
- Adds "in-list" class to all <li> elements
- Automatically detects and adds list-type classes to <ol> elements:
  - list-type-decimal (1, 2, 3...)
  - list-type-lower-alpha (a, b, c...)
  - list-type-upper-alpha (A, B, C...)
  - list-type-lower-roman (i, ii, iii...)
  - list-type-upper-roman (I, II, III...)
  - list-type-lower-greek (α, β, γ...)
- Supports configurable additional classes for ul, ol, and li elements
- Wraps li content in <p> tags with configurable classes (if not already wrapped)
- Adds configurable classes to paragraphs immediately before top-level lists
"""

from typing import Dict, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

# Mapping of CSS list-style-type values to our custom CSS classes
LIST_TYPE_CLASS_MAP: Dict[str, str] = {
    "decimal": "list-type-decimal",
    "lower-alpha": "list-type-lower-alpha",
    "upper-alpha": "list-type-upper-alpha",
    "lower-roman": "list-type-lower-roman",
    "upper-roman": "list-type-upper-roman",
    "lower-greek": "list-type-lower-greek",
}


def _calculate_list_level(element: Tag) -> int:
    """
    Calculate the nesting level of a list element.
    Top-level lists are level 1, nested lists are level 2, etc.
    """
    level = 1
    parent = element.parent

    while parent:
        if isinstance(parent, Tag) and parent.name in ["ul", "ol"]:
            level += 1
        parent = parent.parent

    return level


def _detect_list_type(ol: Tag) -> Optional[str]:
    """
    Detect the list type from an <ol> element.

    Checks for:
    1. Inline style attribute (list-style-type)
    2. type attribute (HTML attribute like type="a", type="A", type="i", type="I")
    3. start attribute combined with type attribute

    Returns the corresponding CSS class name or None if not detected.
    """
    # Check for inline style attribute
    style = ol.get("style", "")
    if style:
        # Parse list-style-type from inline styles
        import re

        match = re.search(r"list-style-type:\s*([^;]+)", style)
        if match:
            list_style_type = match.group(1).strip()
            if list_style_type in LIST_TYPE_CLASS_MAP:
                return LIST_TYPE_CLASS_MAP[list_style_type]

    # Check for type attribute (HTML5/legacy)
    type_attr = ol.get("type")
    if type_attr:
        # Map HTML type attribute to CSS list-style-type
        type_map = {
            "1": "decimal",
            "a": "lower-alpha",
            "A": "upper-alpha",
            "i": "lower-roman",
            "I": "upper-roman",
        }
        list_style_type = type_map.get(type_attr)
        if list_style_type and list_style_type in LIST_TYPE_CLASS_MAP:
            return LIST_TYPE_CLASS_MAP[list_style_type]

    return None


def _wrap_li_content_in_paragraph(
    li: Tag, soup: BeautifulSoup, paragraph_classes: Optional[List[str]] = None
):
    """
    Wrap the content of an <li> element in a <p> tag if not already wrapped.

    Args:
        li: The <li> element to process
        soup: BeautifulSoup instance for creating new tags
        paragraph_classes: Classes to add to the <p> wrapper
    """
    paragraph_classes = paragraph_classes or []

    # Check if li already has a single p tag as its only block-level child
    children = [c for c in li.children if isinstance(c, Tag)]

    # If there's already a single p tag and nothing else significant, skip
    if len(children) == 1 and children[0].name == "p":
        # Just add classes to existing p
        existing_classes = children[0].get("class", [])
        if isinstance(existing_classes, str):
            existing_classes = existing_classes.split()
        merged_classes = list(dict.fromkeys(existing_classes + paragraph_classes))
        if merged_classes:
            children[0]["class"] = merged_classes
        return

    # Check if li contains only inline content or needs wrapping
    has_block_elements = any(
        isinstance(c, Tag) and c.name in ["p", "div", "ul", "ol", "pre", "blockquote"]
        for c in li.children
    )

    # If there are nested lists or block elements, don't wrap everything
    # Only wrap the inline content before the first block element
    if has_block_elements:
        # Collect inline content before first block element
        inline_content = []
        for child in list(li.children):
            if isinstance(child, Tag) and child.name in [
                "ul",
                "ol",
                "pre",
                "blockquote",
            ]:
                # Stop collecting when we hit a block element
                break
            elif isinstance(child, Tag) and child.name == "p":
                # Found a paragraph, add classes and stop
                existing_classes = child.get("class", [])
                if isinstance(existing_classes, str):
                    existing_classes = existing_classes.split()
                merged_classes = list(
                    dict.fromkeys(existing_classes + paragraph_classes)
                )
                if merged_classes:
                    child["class"] = merged_classes
                break
            else:
                inline_content.append(child)

        # If we collected inline content, wrap it
        if inline_content and any(
            (isinstance(c, NavigableString) and c.strip()) or isinstance(c, Tag)
            for c in inline_content
        ):
            p = soup.new_tag("p")
            if paragraph_classes:
                p["class"] = paragraph_classes

            # Move inline content into p
            for item in inline_content:
                if isinstance(item, NavigableString):
                    p.append(item)
                else:
                    item.extract()
                    p.append(item)

            # Insert p as first child of li
            if len(li.contents) > 0:
                li.contents[0].insert_before(p)
            else:
                li.append(p)
    else:
        # No block elements, wrap all content in p
        p = soup.new_tag("p")
        if paragraph_classes:
            p["class"] = paragraph_classes

        # Move all content into p
        for item in list(li.contents):
            p.append(item)

        li.clear()
        li.append(p)


def list_enhancer(
    html: str,
    context: dict,
    ul_classes: Optional[List[str]] = None,
    ol_classes: Optional[List[str]] = None,
    li_classes: Optional[List[str]] = None,
    li_paragraph_classes: Optional[List[str]] = None,
    preceding_paragraph_classes: Optional[List[str]] = None,
    add_list_level_classes: bool = True,
    wrap_li_in_paragraph: bool = True,
    mark_preceding_paragraphs: bool = True,
    mark_big_lists: bool = True,
) -> str:
    """
    Enhance list elements with classes and structure.

    Args:
        html: HTML string to process
        context: Context dictionary (not used currently)
        ul_classes: Additional classes to add to <ul> elements (default: ["list"])
        ol_classes: Additional classes to add to <ol> elements (default: ["list"])
        li_classes: Additional classes to add to <li> elements (default: ["in-list"])
        li_paragraph_classes: Classes to add to <p> wrappers inside <li> (default: [])
        preceding_paragraph_classes: Classes to add to <p> immediately before a list (default: ["list-heading"])
        add_list_level_classes: Add "list-level-n" classes (default: True)
        wrap_li_in_paragraph: Wrap <li> content in <p> tags (default: True)
        mark_preceding_paragraphs: Add classes to paragraphs before lists (default: True)
        mark_big_lists: Add "big-list" class if list items have multiple non-list children (default: True)

    Returns:
        Processed HTML with enhanced list elements
    """
    ul_classes = ul_classes or ["list"]
    ol_classes = ol_classes or ["list"]
    li_classes = li_classes or ["in-list"]
    li_paragraph_classes = li_paragraph_classes or ["in-list"]
    preceding_paragraph_classes = preceding_paragraph_classes or ["list-heading"]

    soup = BeautifulSoup(html, "html.parser")

    def _is_big_list(list_element: Tag) -> bool:
        """
        Check if a list should be marked as a "big-list".
        A list is "big" if any of its direct <li> children have multiple non-list block-level children.
        """
        for li in list_element.find_all("li", recursive=False):
            # Count non-list, non-whitespace children
            non_list_children = []
            for child in li.children:
                # Skip whitespace-only text nodes
                if isinstance(child, NavigableString) and not child.strip():
                    continue
                # Skip nested lists
                if isinstance(child, Tag) and child.name in ["ul", "ol"]:
                    continue
                # Count this child
                if isinstance(child, Tag):
                    non_list_children.append(child)

            # If this li has multiple non-list children, it's a big list
            if len(non_list_children) > 1:
                return True

        return False

    # Process all ul elements
    for ul in soup.find_all("ul"):
        # Add base classes
        existing_classes = ul.get("class", [])
        if isinstance(existing_classes, str):
            existing_classes = existing_classes.split()

        new_classes = list(existing_classes)

        # Add configured ul classes
        for cls in ul_classes:
            if cls not in new_classes:
                new_classes.append(cls)

        # Add level class
        if add_list_level_classes:
            level = _calculate_list_level(ul)
            level_class = f"list-level-{level}"
            if level_class not in new_classes:
                new_classes.append(level_class)

        # Add big-list class if applicable
        if mark_big_lists and _is_big_list(ul):
            if "big-list" not in new_classes:
                new_classes.append("big-list")

        ul["class"] = new_classes

        # Mark preceding paragraph if configured
        # Only mark paragraphs that are NOT inside a list (to exclude nested lists)
        if mark_preceding_paragraphs and preceding_paragraph_classes:
            # Check if this list is NOT nested inside another list
            parent_list = ul.find_parent(["ul", "ol"])
            if not parent_list:
                # This is a top-level list, check for preceding paragraph
                prev_sibling = ul.find_previous_sibling()
                if (
                    prev_sibling
                    and isinstance(prev_sibling, Tag)
                    and prev_sibling.name == "p"
                ):
                    existing_p_classes = prev_sibling.get("class", [])
                    if isinstance(existing_p_classes, str):
                        existing_p_classes = existing_p_classes.split()
                    merged_p_classes = list(
                        dict.fromkeys(existing_p_classes + preceding_paragraph_classes)
                    )
                    prev_sibling["class"] = merged_p_classes

    # Process all ol elements
    for ol in soup.find_all("ol"):
        # Add base classes
        existing_classes = ol.get("class", [])
        if isinstance(existing_classes, str):
            existing_classes = existing_classes.split()

        new_classes = list(existing_classes)

        # Add configured ol classes
        for cls in ol_classes:
            if cls not in new_classes:
                new_classes.append(cls)

        # Add level class
        if add_list_level_classes:
            level = _calculate_list_level(ol)
            level_class = f"list-level-{level}"
            if level_class not in new_classes:
                new_classes.append(level_class)

        # Detect and add list type class
        list_type_class = _detect_list_type(ol)
        if list_type_class and list_type_class not in new_classes:
            new_classes.append(list_type_class)

        # Add big-list class if applicable
        if mark_big_lists and _is_big_list(ol):
            if "big-list" not in new_classes:
                new_classes.append("big-list")

        ol["class"] = new_classes

        # Mark preceding paragraph if configured
        # Only mark paragraphs that are NOT inside a list (to exclude nested lists)
        if mark_preceding_paragraphs and preceding_paragraph_classes:
            # Check if this list is NOT nested inside another list
            parent_list = ol.find_parent(["ul", "ol"])
            if not parent_list:
                # This is a top-level list, check for preceding paragraph
                prev_sibling = ol.find_previous_sibling()
                if (
                    prev_sibling
                    and isinstance(prev_sibling, Tag)
                    and prev_sibling.name == "p"
                ):
                    existing_p_classes = prev_sibling.get("class", [])
                    if isinstance(existing_p_classes, str):
                        existing_p_classes = existing_p_classes.split()
                    merged_p_classes = list(
                        dict.fromkeys(existing_p_classes + preceding_paragraph_classes)
                    )
                    prev_sibling["class"] = merged_p_classes

    # Process all li elements
    for li in soup.find_all("li"):
        # Add base classes to the li element itself
        existing_classes = li.get("class", [])
        if isinstance(existing_classes, str):
            existing_classes = existing_classes.split()

        new_classes = list(existing_classes)

        # Add configured li classes
        for cls in li_classes:
            if cls not in new_classes:
                new_classes.append(cls)

        li["class"] = new_classes

        # Add li_paragraph_classes to all <p> elements within this <li>
        if li_paragraph_classes:
            for p in li.find_all("p", recursive=True):
                existing_p_classes = p.get("class", [])
                if isinstance(existing_p_classes, str):
                    existing_p_classes = existing_p_classes.split()
                merged_p_classes = list(
                    dict.fromkeys(existing_p_classes + li_paragraph_classes)
                )
                p["class"] = merged_p_classes

        # Wrap content in paragraph if configured
        if wrap_li_in_paragraph:
            _wrap_li_content_in_paragraph(li, soup, li_paragraph_classes)

    return str(soup)


def list_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for list_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return list_enhancer(
        html,
        context,
        ul_classes=["list"],
        ol_classes=["list"],
        li_classes=["in-list"],
        li_paragraph_classes=[],
        preceding_paragraph_classes=["list-heading", "block"],
        add_list_level_classes=True,
        wrap_li_in_paragraph=True,
        mark_preceding_paragraphs=True,
        mark_big_lists=True,
    )
