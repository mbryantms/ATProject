# engine/markdown/postprocessors/block_marker.py
"""
Postprocessor that marks discrete blocks of content with a "block" class.

This postprocessor:
- Adds a configurable CSS class to outermost elements representing discrete content blocks
- Works with paragraphs, sections, lists, figures, blockquotes, and other block-level elements
- Only marks the outermost element to avoid redundant marking of nested content
- Configurable list of block-level element types to process
"""

from typing import List, Optional, Set

from bs4 import BeautifulSoup, Tag

# Default block-level elements that represent discrete content blocks
DEFAULT_BLOCK_ELEMENTS = [
    "p",
    "section",
    "ul",
    "ol",
    "figure",
    "blockquote",
    "pre",
    "table",
    "div",
    "hr",
    "dl",  # Definition list
]


def block_marker(
    html: str,
    context: dict,
    block_class: Optional[List[str]] = None,
    block_elements: Optional[List[str]] = None,
    skip_nested: bool = True,
) -> str:
    """
    Add a class to discrete block-level content elements.

    Args:
        html: HTML string to process
        context: Context dictionary (checks for 'is_abstract' flag)
        block_class: CSS classes to add to block elements (default: ["block"])
        block_elements: List of element types to mark as blocks (default: DEFAULT_BLOCK_ELEMENTS)
        skip_nested: Skip elements that are nested within other marked blocks (default: True)

    Returns:
        Processed HTML with block elements marked
    """
    # If rendering an abstract, skip adding block classes to paragraphs
    is_abstract = context.get("is_abstract", False)

    block_class = block_class or ["block"]
    block_elements = block_elements or DEFAULT_BLOCK_ELEMENTS

    soup = BeautifulSoup(html, "html.parser")

    # Convert to set for faster lookups
    block_element_set: Set[str] = set(block_elements)

    # Track which elements we've already marked to avoid redundant marking
    marked_elements: Set[Tag] = set()

    def is_nested_in_block(element: Tag) -> bool:
        """
        Check if an element is nested within another block element we're marking.

        Special handling:
        - Paragraphs: Allow within sections/headers, skip within lists (ul, ol, li) and blockquotes
        - Lists (ul, ol): Allow outermost lists within sections/headers, skip nested lists
        - First paragraph in backlinks or abstract sections: Skip block class
        """
        is_paragraph = element.name == "p"
        is_list = element.name in ["ul", "ol"]
        parent = element.parent

        while parent and parent.name != "[document]":
            if isinstance(parent, Tag):
                # Special case for paragraphs
                if is_paragraph:
                    # Skip paragraphs that are within lists or blockquotes
                    if parent.name in ["ul", "ol", "li", "blockquote"]:
                        return True
                    # Allow paragraphs within sections/headers (continue checking)
                    if parent.name in ["section", "header"]:
                        parent = parent.parent
                        continue

                # Special case for lists (ul, ol)
                if is_list:
                    # Skip lists that are nested within other lists
                    if parent.name in ["ul", "ol", "li"]:
                        return True
                    # Skip lists that are within blockquotes
                    if parent.name == "blockquote":
                        return True
                    # Allow outermost lists within sections/headers (continue checking)
                    if parent.name in ["section", "header"]:
                        parent = parent.parent
                        continue

                # For non-paragraph, non-list elements, check if nested in any block element
                if parent.name in block_element_set:
                    # Check if this parent has already been marked or will be marked
                    if parent in marked_elements:
                        return True
                    # Check if parent already has the block class
                    existing_classes = parent.get("class", [])
                    if isinstance(existing_classes, str):
                        existing_classes = existing_classes.split()
                    if any(cls in block_class for cls in existing_classes):
                        return True

            parent = parent.parent
        return False

    # Find all elements that match our block element types
    for element_type in block_elements:
        for element in soup.find_all(element_type):
            # Skip paragraphs if rendering an abstract
            if is_abstract and element.name == "p":
                continue

            # Skip if we should skip nested elements and this is nested
            if skip_nested and is_nested_in_block(element):
                continue

            # Add the block class
            existing_classes = element.get("class", [])
            if isinstance(existing_classes, str):
                existing_classes = existing_classes.split()

            # Only add if not already present
            merged_classes = list(dict.fromkeys(existing_classes + block_class))
            element["class"] = merged_classes

            # Mark this element as processed
            marked_elements.add(element)

    return str(soup)


def block_marker_default(html: str, context: dict) -> str:
    """
    Default configuration for block_marker.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return block_marker(
        html,
        context,
        block_class=["block"],
        block_elements=DEFAULT_BLOCK_ELEMENTS,
        skip_nested=True,
    )
