# engine/markdown/postprocessors/typography_enhancer.py
"""
Postprocessor that enhances typography elements with specialized formatting.

This postprocessor handles various typography enhancements:
- Wraps adjacent <sub> and <sup> elements in a span with "subsup" class
- Adds word-break opportunities (<wbr> tags) after slashes in long URLs/paths
- Cleans up consecutive <wbr> tags
- Normalizes non-breaking spaces in appropriate contexts

Note: Smart quotes, em/en dashes, and ellipses are handled by Pandoc's 'smart'
extension during markdown rendering, so they are NOT implemented here.
"""

import re
from typing import List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag


def _wrap_subsup_pairs(soup: BeautifulSoup) -> None:
    """
    Find adjacent <sub> and <sup> elements and wrap them in a span.subsup.

    The sub and sup can be in either order. They must be siblings with at most
    whitespace between them.
    """
    # Find all sub elements
    for sub in soup.find_all("sub"):
        # Check next sibling (skipping whitespace)
        next_sibling = sub.next_sibling
        while next_sibling and isinstance(next_sibling, NavigableString):
            if next_sibling.strip():
                # Non-whitespace text, stop looking
                break
            next_sibling = next_sibling.next_sibling

        if next_sibling and isinstance(next_sibling, Tag) and next_sibling.name == "sup":
            # Found sub followed by sup
            _create_subsup_wrapper(soup, sub, next_sibling)
            continue

    # Find all sup elements (to catch sup followed by sub)
    for sup in soup.find_all("sup"):
        # Skip if already wrapped
        if sup.parent and sup.parent.name == "span" and "subsup" in sup.parent.get("class", []):
            continue

        # Check next sibling (skipping whitespace)
        next_sibling = sup.next_sibling
        while next_sibling and isinstance(next_sibling, NavigableString):
            if next_sibling.strip():
                # Non-whitespace text, stop looking
                break
            next_sibling = next_sibling.next_sibling

        if next_sibling and isinstance(next_sibling, Tag) and next_sibling.name == "sub":
            # Found sup followed by sub
            _create_subsup_wrapper(soup, sup, next_sibling)


def _create_subsup_wrapper(soup: BeautifulSoup, first: Tag, second: Tag) -> None:
    """
    Create a span.subsup wrapper around two elements.

    Args:
        soup: BeautifulSoup instance
        first: First element (sub or sup)
        second: Second element (sup or sub)
    """
    # Check if already wrapped
    if first.parent and first.parent.name == "span" and "subsup" in first.parent.get("class", []):
        return

    # Create wrapper span
    wrapper = soup.new_tag("span")
    wrapper["class"] = ["subsup"]

    # Insert wrapper before the first element
    first.insert_before(wrapper)

    # Extract both elements and any whitespace between them
    current = first
    elements_to_move = []

    while current:
        if current == second:
            elements_to_move.append(current)
            break
        elements_to_move.append(current)
        current = current.next_sibling

    # Move all elements into the wrapper
    for elem in elements_to_move:
        elem.extract()
        wrapper.append(elem)


def _add_word_breaks(soup: BeautifulSoup) -> None:
    """
    Add <wbr> (word break opportunity) tags after slashes in long URLs/paths.

    This helps long URLs and file paths wrap more gracefully.
    - Processes inline <code> elements (for URLs in code)
    - Excludes <pre> blocks (code blocks)
    - Excludes <script>, <style>, <noscript> tags
    """
    excluded_tags = {'pre', 'script', 'style', 'noscript'}

    def should_process_element(element):
        """
        Check if element should be processed for word breaks.

        Returns True for:
        - Regular text
        - Inline <code> elements

        Returns False for:
        - Text within <pre> blocks
        - Text within <script>, <style>, <noscript> tags
        """
        current = element
        while current:
            if isinstance(current, Tag) and current.name in excluded_tags:
                return False
            current = current.parent
        return True

    # Find all text nodes and add word breaks after slashes
    def process_text_node(text_node):
        """Process a text node and insert <wbr> tags after slashes."""
        if not isinstance(text_node, NavigableString):
            return

        if not should_process_element(text_node):
            return

        text = str(text_node)

        # Only process if there are slashes followed by non-slash characters
        # Pattern: slash(es) followed by non-slash, non-wbr character
        if not re.search(r'/+[^/\u200b]', text):
            return

        # Split on slashes while keeping them
        parts = re.split(r'(/+)', text)

        # If no splitting occurred or only one part, nothing to do
        if len(parts) <= 1:
            return

        # Create replacement nodes
        new_nodes = []
        for i, part in enumerate(parts):
            if not part:  # Skip empty parts
                continue

            # Add the text part
            new_nodes.append(soup.new_string(part))

            # Add <wbr> after slash sequences (but not at the end)
            if part.startswith('/') and i < len(parts) - 1 and parts[i + 1]:
                wbr = soup.new_tag('wbr')
                new_nodes.append(wbr)

        # Replace the original text node with new nodes
        if len(new_nodes) > 1:  # Only replace if we actually added <wbr> tags
            parent = text_node.parent
            if parent:
                # Insert all new nodes before the original
                for node in new_nodes:
                    text_node.insert_before(node)
                # Remove the original text node
                text_node.extract()

    # Process all text nodes in the document
    # We need to collect them first because we'll be modifying the tree
    text_nodes = []
    for element in soup.descendants:
        if isinstance(element, NavigableString) and not isinstance(element, (Tag,)):
            text_nodes.append(element)

    for text_node in text_nodes:
        process_text_node(text_node)


def _clean_consecutive_wbr_tags(soup: BeautifulSoup) -> None:
    """
    Remove consecutive <wbr> tags, keeping only one.

    Also removes <wbr> tags that are only separated by whitespace-only text nodes.
    """
    for wbr in soup.find_all('wbr'):
        # Check next sibling
        next_sibling = wbr.next_sibling

        # Skip whitespace-only text nodes
        while next_sibling and isinstance(next_sibling, NavigableString):
            if next_sibling.strip():  # Non-whitespace text, stop
                break
            next_sibling = next_sibling.next_sibling

        # If next non-whitespace sibling is also a <wbr>, remove this one
        if next_sibling and isinstance(next_sibling, Tag) and next_sibling.name == 'wbr':
            wbr.extract()


def _normalize_nbsp(soup: BeautifulSoup) -> None:
    """
    Convert non-breaking spaces (&nbsp; / \\xa0) to regular spaces in appropriate contexts.

    Preserves non-breaking spaces in:
    - <code> and <pre> elements
    - Between numbers and units
    - In specific formatting contexts
    """
    excluded_tags = {'pre', 'code'}

    def should_process_element(element):
        """Check if element or any parent is in excluded tags."""
        current = element
        while current:
            if isinstance(current, Tag) and current.name in excluded_tags:
                return False
            current = current.parent
        return True

    # Find all text nodes with non-breaking spaces
    for element in soup.descendants:
        if isinstance(element, NavigableString) and '\xa0' in str(element):
            if should_process_element(element):
                # Replace nbsp with regular space
                # Preserve nbsp in specific patterns (number + unit, etc.)
                text = str(element)
                # Don't replace nbsp between digit and letter (like "5 km")
                text = re.sub(r'(?<![0-9])\xa0(?![A-Za-z])', ' ', text)
                element.replace_with(text)


def typography_enhancer(
    html: str,
    context: dict,
    wrap_subsup_pairs: bool = True,
    add_word_breaks: bool = True,
    normalize_nbsp: bool = True,
) -> str:
    """
    Enhance typography elements with specialized formatting.

    Note: Smart quotes, em/en dashes, and ellipses are already handled by
    Pandoc's 'smart' extension during markdown rendering.

    Args:
        html: HTML string to process
        context: Context dictionary (not used currently)
        wrap_subsup_pairs: Wrap adjacent sub/sup pairs in span.subsup (default: True)
        add_word_breaks: Add <wbr> tags after slashes for better URL wrapping (default: True)
        normalize_nbsp: Convert non-breaking spaces to regular spaces where appropriate (default: True)

    Returns:
        Processed HTML with enhanced typography
    """
    soup = BeautifulSoup(html, "html.parser")

    # Apply typography enhancements
    if wrap_subsup_pairs:
        _wrap_subsup_pairs(soup)

    if add_word_breaks:
        _add_word_breaks(soup)
        # Clean up any consecutive <wbr> tags that may have been created
        _clean_consecutive_wbr_tags(soup)

    if normalize_nbsp:
        _normalize_nbsp(soup)

    return str(soup)


def typography_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for typography_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return typography_enhancer(
        html,
        context,
        wrap_subsup_pairs=True,
        add_word_breaks=True,
        normalize_nbsp=True,
    )