# engine/markdown/postprocessors/blockquote_enhancer.py
"""
Postprocessor that enhances blockquote elements with nesting level classes and float support.

This postprocessor:
- Adds "blockquote-level-n" class to <blockquote> elements based on nesting depth
- Level 1 for top-level blockquotes, level 2 for nested, etc.
- Supports configurable additional classes for blockquotes
- Detects float markers in blockquote content and wraps with float divs
- Float markers: {>>} for float-right, {<<} for float-left (at start of blockquote)
"""

import re
from typing import List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag


def _calculate_blockquote_level(blockquote: Tag) -> int:
    """
    Calculate the nesting level of a blockquote element.
    Top-level blockquotes are level 1, nested blockquotes are level 2, etc.
    """
    level = 1
    parent = blockquote.parent

    while parent:
        if isinstance(parent, Tag) and parent.name == "blockquote":
            level += 1
        parent = parent.parent

    return level


def _detect_and_remove_float_marker(blockquote: Tag) -> Optional[str]:
    """
    Detect float marker at the start of a blockquote and remove it.

    Looks for {>>} (float-right) or {<<} (float-left) at the beginning
    of the first text content or paragraph in the blockquote.

    Args:
        blockquote: The blockquote element to check

    Returns:
        "right" if {>>} found, "left" if {<<} found, None otherwise
    """
    # Pattern to match float markers at the start of text
    float_right_pattern = re.compile(r'^\s*\{>>\}\s*')
    float_left_pattern = re.compile(r'^\s*\{<<\}\s*')

    # Check the first meaningful content in the blockquote
    for child in blockquote.children:
        # Skip whitespace-only text nodes
        if isinstance(child, NavigableString):
            text = str(child)
            if not text.strip():
                continue

            # Check for float markers
            if float_right_pattern.match(text):
                # Remove the marker from the text
                new_text = float_right_pattern.sub('', text)
                child.replace_with(new_text)
                return "right"
            elif float_left_pattern.match(text):
                # Remove the marker from the text
                new_text = float_left_pattern.sub('', text)
                child.replace_with(new_text)
                return "left"

        elif isinstance(child, Tag):
            # Check inside first paragraph or similar element
            if child.name in ["p", "div"]:
                # Check the first text content of this element
                if child.string:
                    text = str(child.string)
                    if float_right_pattern.match(text):
                        new_text = float_right_pattern.sub('', text)
                        child.string.replace_with(new_text)
                        return "right"
                    elif float_left_pattern.match(text):
                        new_text = float_left_pattern.sub('', text)
                        child.string.replace_with(new_text)
                        return "left"
                else:
                    # Check first child if no direct string
                    for grandchild in child.children:
                        if isinstance(grandchild, NavigableString):
                            text = str(grandchild)
                            if not text.strip():
                                continue
                            if float_right_pattern.match(text):
                                new_text = float_right_pattern.sub('', text)
                                grandchild.replace_with(new_text)
                                return "right"
                            elif float_left_pattern.match(text):
                                new_text = float_left_pattern.sub('', text)
                                grandchild.replace_with(new_text)
                                return "left"
                            break
            # Stop at first non-whitespace element
            break

    return None


def blockquote_enhancer(
    html: str,
    context: dict,
    blockquote_classes: Optional[List[str]] = None,
    add_level_classes: bool = True,
    enable_float_detection: bool = True,
) -> str:
    """
    Enhance blockquote elements with nesting level classes and float support.

    Args:
        html: HTML string to process
        context: Context dictionary (not used currently)
        blockquote_classes: Additional classes to add to <blockquote> elements (default: [])
        add_level_classes: Add "blockquote-level-n" classes (default: True)
        enable_float_detection: Detect and process float markers (default: True)

    Returns:
        Processed HTML with enhanced blockquote elements
    """
    blockquote_classes = blockquote_classes or []

    soup = BeautifulSoup(html, "html.parser")

    # Process all blockquote elements
    for blockquote in soup.find_all("blockquote"):
        # Check for float marker and remove it
        float_direction = None
        if enable_float_detection:
            float_direction = _detect_and_remove_float_marker(blockquote)

        # Get existing classes
        existing_classes = blockquote.get("class", [])
        if isinstance(existing_classes, str):
            existing_classes = existing_classes.split()

        new_classes = list(existing_classes)

        # Add configured blockquote classes
        for cls in blockquote_classes:
            if cls not in new_classes:
                new_classes.append(cls)

        # Add level class
        if add_level_classes:
            level = _calculate_blockquote_level(blockquote)
            level_class = f"blockquote-level-{level}"
            if level_class not in new_classes:
                new_classes.append(level_class)

        blockquote["class"] = new_classes

        # Wrap in float div if float direction detected
        if float_direction:
            # Create wrapper div
            float_div = soup.new_tag("div")
            float_div["class"] = ["float", f"float-{float_direction}"]

            # Replace blockquote with wrapper in its current position
            blockquote.insert_before(float_div)
            blockquote.extract()
            float_div.append(blockquote)

    return str(soup)


def blockquote_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for blockquote_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return blockquote_enhancer(
        html,
        context,
        blockquote_classes=[],
        add_level_classes=True,
        enable_float_detection=True,
    )