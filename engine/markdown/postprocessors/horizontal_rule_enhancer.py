# engine/markdown/postprocessors/horizontal_rule_enhancer.py
"""
Postprocessor that enhances horizontal rule elements with style classes.

This postprocessor:
- Adds style classes to <hr> elements for custom SVG background styling
- Supports three distinct styles: horizontal-rule-1, horizontal-rule-2, horizontal-rule-3
- Detects style hints from HTML comments preceding the <hr> element
- Cycles through styles automatically if no hint is provided

Usage in Markdown:
    <!-- hr:1 -->
    ---

    <!-- hr:2 -->
    ***

    <!-- hr:3 -->
    ___

    Or just use --- and styles will cycle automatically
"""

import re
from typing import List, Optional

from bs4 import BeautifulSoup, Comment, NavigableString, Tag


def horizontal_rule_enhancer(
    html: str,
    context: dict,
    enable_style_cycling: bool = True,
    default_style: int = 1,
) -> str:
    """
    Enhance horizontal rule elements with style classes.

    Args:
        html: HTML string to process
        context: Context dictionary (not used currently)
        enable_style_cycling: Automatically cycle through styles (default: True)
        default_style: Default style number 1-3 (default: 1)

    Returns:
        Processed HTML with enhanced hr elements
    """
    soup = BeautifulSoup(html, "html.parser")

    # Pattern to detect style hints in HTML comments
    style_hint_pattern = re.compile(r'hr:([123])', re.IGNORECASE)

    # Track which style to use for cycling
    current_style = default_style
    style_count = 3

    # Find all hr elements
    for hr in soup.find_all("hr"):
        style_number = None

        # Check for preceding HTML comment with style hint
        prev_sibling = hr.find_previous_sibling()

        # Look backwards through siblings to find a comment
        check_sibling = prev_sibling
        while check_sibling:
            # Skip whitespace-only text nodes
            if isinstance(check_sibling, NavigableString) and not str(check_sibling).strip():
                check_sibling = check_sibling.find_previous_sibling()
                continue

            # Check if it's a comment
            if isinstance(check_sibling, Comment):
                match = style_hint_pattern.search(str(check_sibling))
                if match:
                    style_number = int(match.group(1))
                    # Remove the comment since we've processed it
                    check_sibling.extract()
                break

            # Stop at first non-whitespace, non-comment element
            break

        # If no style hint found, use cycling or default
        if style_number is None:
            if enable_style_cycling:
                style_number = current_style
                current_style = (current_style % style_count) + 1
            else:
                style_number = default_style

        # Validate style number
        if style_number not in [1, 2, 3]:
            style_number = default_style

        # Add style class
        existing_classes = hr.get("class", [])
        if isinstance(existing_classes, str):
            existing_classes = existing_classes.split()

        style_class = f"horizontal-rule-{style_number}"

        # Add classes: block, horizontal-rule, and horizontal-rule-N
        new_classes = list(existing_classes)
        if "block" not in new_classes:
            new_classes.append("block")
        if "horizontal-rule" not in new_classes:
            new_classes.append("horizontal-rule")
        if style_class not in new_classes:
            new_classes.append(style_class)

        hr["class"] = new_classes

    return str(soup)


def horizontal_rule_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for horizontal_rule_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return horizontal_rule_enhancer(
        html,
        context,
        enable_style_cycling=True,
        default_style=1,
    )