# engine/markdown/postprocessors/header_sectionizer.py
"""
Postprocessor that wraps headers in section elements with hierarchical nesting.

This postprocessor:
- Adds configurable CSS classes to header elements (h1-h6)
- Wraps each header and its content in a <section> element
- Assigns the header's id to the section wrapper
- Adds level-based classes (level1, level2, etc.) to sections
- Supports configurable additional classes for sections
- Properly nests sections based on header hierarchy
"""

import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

_HEADING_TAGS = {f"h{i}" for i in range(1, 7)}


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.strip().lower()
    # Replace apostrophes and similar quotes
    text = re.sub(r"[''\"]", "", text)
    # Replace non-alphanumeric with dashes
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Collapse multiple dashes
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or "section"


def _get_text_content(element: Tag) -> str:
    """Extract text content from an element."""
    return element.get_text().strip()


def header_sectionizer(
    html: str,
    context: dict,
    header_classes: Optional[List[str]] = None,
    section_classes: Optional[List[str]] = None,
    add_data_attributes: bool = True,
    set_heading_id: bool = True,
) -> str:
    """
    Wrap headers in hierarchical section elements.

    Args:
        html: HTML string to process
        context: Context dictionary (not used currently)
        header_classes: CSS classes to add to header elements (default: ["heading"])
        section_classes: CSS classes to add to section wrappers (default: ["block"])
        add_data_attributes: Add data-level and data-slug attributes (default: True)
        set_heading_id: Set id attribute on header elements (default: True)

    Returns:
        Processed HTML with headers wrapped in sections
    """
    header_classes = header_classes or ["heading"]
    section_classes = section_classes or ["block"]

    soup = BeautifulSoup(html, "html.parser")
    used_slugs: Dict[str, int] = {}

    def unique_slug(base: str) -> str:
        """Generate unique slug by appending counter if needed."""
        count = used_slugs.get(base, 0)
        if count == 0:
            used_slugs[base] = 1
            return base
        # Already used; increment and append
        count += 1
        used_slugs[base] = count
        return f"{base}-{count}"

    def process_container(parent: Tag, start_index: int = 0):
        """Recursively process a container and wrap headers in sections."""
        i = start_index
        while True:
            children = list(parent.children)
            # Filter out NavigableString objects that are just whitespace
            children = [
                c
                for c in children
                if not (isinstance(c, NavigableString) and not c.strip())
            ]

            if i >= len(children):
                break

            node = children[i]

            # Skip non-Tag elements
            if not isinstance(node, Tag):
                i += 1
                continue

            tag = node.name.lower() if node.name else ""

            if tag in _HEADING_TAGS:
                level = int(tag[1])
                heading_text = _get_text_content(node)
                base_slug = _slugify(heading_text)
                slug = unique_slug(base_slug)

                # Add classes to the header element
                existing_classes = node.get("class", [])
                if isinstance(existing_classes, str):
                    existing_classes = existing_classes.split()
                merged_classes = list(dict.fromkeys(existing_classes + header_classes))
                node["class"] = merged_classes

                # Set header id if configured and not already present
                if set_heading_id and not node.get("id"):
                    node["id"] = slug

                # Add data attributes to header
                if add_data_attributes:
                    node["data-level"] = str(level)
                    node["data-slug"] = slug

                # Convert header content into an anchor link
                # Check if header already contains a single anchor tag
                existing_children = list(node.children)
                only_child_is_anchor = (
                    len(existing_children) == 1
                    and isinstance(existing_children[0], Tag)
                    and existing_children[0].name == "a"
                    and (not node.string or not node.string.strip())
                )

                if not only_child_is_anchor:
                    # Create anchor element
                    anchor = soup.new_tag("a")
                    anchor["href"] = f"#{slug}"
                    anchor["title"] = f"Link to section: § '{heading_text}'"

                    # Move all header content (text and child elements like <strong>, <em>) into anchor
                    # Use contents to get everything including text nodes and element nodes
                    for item in list(node.contents):
                        # Extract and append each item (preserves formatting tags)
                        anchor.append(item)

                    # Clear the header and add anchor as only child
                    node.clear()
                    node.append(anchor)
                else:
                    # Update existing anchor
                    anchor = existing_children[0]
                    anchor["href"] = f"#{slug}"
                    anchor["title"] = f"Link to section: § '{heading_text}'"

                # Create section wrapper
                section = soup.new_tag("section")

                # Build section classes: section_classes + levelN
                section_class_list = list(
                    dict.fromkeys(section_classes + [f"level{level}"])
                )
                section["class"] = section_class_list
                section["id"] = slug

                if add_data_attributes:
                    section["data-level"] = str(level)
                    section["data-slug"] = slug

                # Replace header node with section in parent
                node.insert_before(section)
                node.extract()
                section.append(node)

                # Gather following siblings into this section until we hit a header
                # of the same or higher level (lower number)
                while True:
                    # Refresh children list
                    remaining = list(parent.children)
                    remaining = [
                        c
                        for c in remaining
                        if not (isinstance(c, NavigableString) and not c.strip())
                    ]

                    # Find the section we just created
                    try:
                        section_idx = remaining.index(section)
                    except ValueError:
                        break

                    # Check if there's a next sibling
                    if section_idx + 1 >= len(remaining):
                        break

                    next_node = remaining[section_idx + 1]

                    # Skip non-Tag elements
                    if not isinstance(next_node, Tag):
                        next_node.extract()
                        section.append(next_node)
                        continue

                    next_tag = next_node.name.lower() if next_node.name else ""

                    # If it's a header of same or higher level, stop
                    if next_tag in _HEADING_TAGS:
                        next_level = int(next_tag[1])
                        if next_level <= level:
                            break

                    # Move next node into section
                    next_node.extract()
                    section.append(next_node)

                # Recursively process the section contents (skip first child which is the header)
                process_container(section, start_index=1)

                # Don't increment i since we've moved nodes around
                # Just continue from current position

            else:
                i += 1

    # Process the root level
    process_container(soup, start_index=0)

    return str(soup)


def header_sectionizer_default(html: str, context: dict) -> str:
    """
    Default configuration for header_sectionizer matching the original extension.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return header_sectionizer(
        html,
        context,
        header_classes=["heading"],
        section_classes=["block"],
        add_data_attributes=True,
        set_heading_id=True,
    )
