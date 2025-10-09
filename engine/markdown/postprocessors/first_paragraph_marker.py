# engine/markdown/postprocessors/first_paragraph_marker.py
"""
Postprocessor that marks the first paragraph in various contexts.

This postprocessor:
- Adds a configurable CSS class to the first <p> element within each <section>
- Adds the class to the first <p> after headings (h1-h6)
- Adds the class to the first <p> after ordered or unordered lists
- Adds the class to the first <p> within <li> elements
- Adds the class to the first <p> within <blockquote> elements (including nested blockquotes)
- Adds the class to the first <p> after images, figures, blockquotes, divs, or horizontal rules
- Works recursively for nested structures
"""

from typing import List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag


def _add_class_to_paragraph(p: Tag, classes: List[str]) -> None:
    """Helper function to add classes to a paragraph element."""
    existing_classes = p.get("class", [])
    if isinstance(existing_classes, str):
        existing_classes = existing_classes.split()
    merged_classes = list(dict.fromkeys(existing_classes + classes))
    p["class"] = merged_classes


def _find_first_paragraph_in_children(
    parent: Tag, skip_elements: Optional[List[str]] = None
) -> Optional[Tag]:
    """
    Find the first <p> element among the children of a parent element.

    Args:
        parent: The parent element to search
        skip_elements: List of tag names to skip over (e.g., ['h1', 'h2', ...])

    Returns:
        The first <p> tag found, or None
    """
    skip_elements = skip_elements or []

    for child in parent.children:
        # Skip whitespace-only text nodes
        if isinstance(child, NavigableString) and not child.strip():
            continue

        if not isinstance(child, Tag):
            continue

        # If it's a paragraph, return it
        if child.name == "p":
            return child

        # Skip specified elements (like headings) but continue searching
        if child.name in skip_elements:
            continue

        # For any other element, stop searching
        break

    return None


def first_paragraph_marker(
    html: str,
    context: dict,
    first_paragraph_class: Optional[List[str]] = None,
) -> str:
    """
    Add a class to the first paragraph element in various contexts.

    Args:
        html: HTML string to process
        context: Context dictionary (checks for 'is_abstract' flag)
        first_paragraph_class: CSS classes to add to first paragraph (default: ["first-graf"])

    Returns:
        Processed HTML with first paragraphs marked
    """
    first_paragraph_class = first_paragraph_class or ["first-graf"]
    is_abstract = context.get("is_abstract", False)

    soup = BeautifulSoup(html, "html.parser")

    # If rendering an abstract, mark the first paragraph directly
    if is_abstract:
        first_p = soup.find("p")
        if first_p:
            _add_class_to_paragraph(first_p, first_paragraph_class)
        return str(soup)

    # 1. Mark first paragraph in each section
    for section in soup.find_all("section"):
        first_p = _find_first_paragraph_in_children(
            section, skip_elements=["h1", "h2", "h3", "h4", "h5", "h6"]
        )
        if first_p:
            _add_class_to_paragraph(first_p, first_paragraph_class)

    # 2. Mark first paragraph after each heading (h1-h6)
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        # Find the next sibling that is a paragraph
        next_sibling = heading.find_next_sibling()
        while next_sibling:
            # Skip whitespace-only text nodes
            if isinstance(next_sibling, NavigableString) and not next_sibling.strip():
                next_sibling = next_sibling.find_next_sibling()
                continue

            if isinstance(next_sibling, Tag):
                if next_sibling.name == "p":
                    _add_class_to_paragraph(next_sibling, first_paragraph_class)
                    break
                # Stop at any other block element
                break

            next_sibling = next_sibling.find_next_sibling()

    # 3. Mark first paragraph after each list (ul, ol)
    for list_elem in soup.find_all(["ul", "ol"]):
        # Find the next sibling that is a paragraph
        next_sibling = list_elem.find_next_sibling()
        while next_sibling:
            # Skip whitespace-only text nodes
            if isinstance(next_sibling, NavigableString) and not next_sibling.strip():
                next_sibling = next_sibling.find_next_sibling()
                continue

            if isinstance(next_sibling, Tag):
                if next_sibling.name == "p":
                    _add_class_to_paragraph(next_sibling, first_paragraph_class)
                    break
                # Stop at any other block element
                break

            next_sibling = next_sibling.find_next_sibling()

    # 4. Mark first paragraph within each <li> element
    for li in soup.find_all("li"):
        first_p = _find_first_paragraph_in_children(li)
        if first_p:
            _add_class_to_paragraph(first_p, first_paragraph_class)

    # 5. Mark first paragraph within each <blockquote> element (including nested)
    for blockquote in soup.find_all("blockquote"):
        first_p = _find_first_paragraph_in_children(blockquote)
        if first_p:
            _add_class_to_paragraph(first_p, first_paragraph_class)

    # 6. Mark first paragraph after images, figures, blockquotes, divs, or hrs
    for element in soup.find_all(["img", "figure", "blockquote", "div", "hr"]):
        # Find the next sibling that is a paragraph
        next_sibling = element.find_next_sibling()
        while next_sibling:
            # Skip whitespace-only text nodes
            if isinstance(next_sibling, NavigableString) and not next_sibling.strip():
                next_sibling = next_sibling.find_next_sibling()
                continue

            if isinstance(next_sibling, Tag):
                if next_sibling.name == "p":
                    _add_class_to_paragraph(next_sibling, first_paragraph_class)
                    break
                # Stop at any other block element
                break

            next_sibling = next_sibling.find_next_sibling()

    return str(soup)


def first_paragraph_marker_default(html: str, context: dict) -> str:
    """
    Default configuration for first_paragraph_marker.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return first_paragraph_marker(
        html,
        context,
        first_paragraph_class=["first-graf"],
    )
