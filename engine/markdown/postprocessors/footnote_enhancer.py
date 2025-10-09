# engine/markdown/postprocessors/footnote_enhancer.py
"""
Postprocessor that enhances footnotes with additional structure and self-links.

This postprocessor:
- Adds a "block" class to the footnotes section
- Adds a section self-link after the <hr> in the footnotes section
- Adds "footnote" class to each footnote list item
- Adds self-links to each individual footnote
- Adds "first-graf" class to the first paragraph in each footnote
"""

from bs4 import BeautifulSoup


def footnote_enhancer(html: str, context: dict) -> str:
    """
    Enhance footnotes with additional structure and self-links.

    Args:
        html: HTML string to process
        context: Context dictionary (may contain base_url for links)

    Returns:
        Processed HTML with enhanced footnotes
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find the footnotes section
    # Pandoc creates a section with id="footnotes" and class="footnotes"
    footnotes_container = soup.find("section", id="footnotes")

    # Fallback: try to find by class
    if not footnotes_container:
        footnotes_container = soup.find("section", class_="footnotes")

    # Fallback: try div with class footnotes
    if not footnotes_container:
        footnotes_container = soup.find("div", class_="footnotes")

    if not footnotes_container:
        # No footnotes found, return unchanged
        return str(soup)

    # Add "block" class to the footnotes container
    if footnotes_container.name == "div":
        # If it's a div, we might want to wrap it in a section or just add the class
        if "class" in footnotes_container.attrs:
            footnotes_container["class"].append("block")
        else:
            footnotes_container["class"] = ["block"]
    elif footnotes_container.name == "section":
        if "class" in footnotes_container.attrs:
            if "block" not in footnotes_container["class"]:
                footnotes_container["class"].append("block")
        else:
            footnotes_container["class"] = ["block"]

    # Find the <hr> in the footnotes section (if it exists)
    hr = footnotes_container.find("hr")
    if hr:
        # Get base URL from context, or use empty string
        base_url = context.get("base_url", "")

        # Create section self-link
        section_link = soup.new_tag("a")
        section_link["class"] = ["section-self-link", "graf-content-not"]
        section_link["href"] = f"{base_url}#footnotes"
        section_link["title"] = "Link to section: § 'Footnotes'"

        # Insert the link after the <hr>
        hr.insert_after(section_link)

    # Find all footnote list items
    # Look for <ol> inside the footnotes container
    ol = footnotes_container.find("ol")
    if ol:
        footnote_items = ol.find_all("li", recursive=False)

        for idx, li in enumerate(footnote_items, start=1):
            # Add "footnote" and "block" classes to the list item
            if "class" in li.attrs:
                if "footnote" not in li["class"]:
                    li["class"].append("footnote")
                if "block" not in li["class"]:
                    li["class"].append("block")
            else:
                li["class"] = ["footnote", "block"]

            # Get the footnote ID from the li element
            # Typically it's something like "fn1", "fn2", etc.
            footnote_id = li.get("id")
            if not footnote_id:
                # Try to infer from the index
                footnote_id = f"fn{idx}"

            # Get base URL from context
            base_url = context.get("base_url", "")

            # Create self-link for this footnote
            footnote_link = soup.new_tag("a")
            footnote_link["href"] = f"{base_url}#{footnote_id}"
            footnote_link["title"] = f"Link to footnote {idx}"
            footnote_link["class"] = ["footnote-self-link", "graf-content-not"]
            footnote_link.string = "\u00a0"  # Non-breaking space

            # Insert the link at the very beginning of the li element
            # Before any child elements (including <p> tags)
            if li.contents:
                # Insert before the first child
                first_child = li.contents[0]
                first_child.insert_before(footnote_link)
            else:
                li.append(footnote_link)

            # Add "first-graf" class to the first <p> element in this footnote
            first_p = li.find("p")
            if first_p:
                if "class" in first_p.attrs:
                    if "first-graf" not in first_p["class"]:
                        first_p["class"].append("first-graf")
                else:
                    first_p["class"] = ["first-graf"]

            # Find and modify the footnote-back link
            footnote_back = li.find("a", class_="footnote-back")
            if footnote_back:
                # Get the original href (e.g., "#fnref1")
                original_href = footnote_back.get("href", "")

                # Update href with base_url
                if original_href:
                    footnote_back["href"] = f"{base_url}{original_href}"

                # Ensure role attribute is set
                if "role" not in footnote_back.attrs:
                    footnote_back["role"] = "doc-backlink"

                # Add style attribute (empty for now)
                footnote_back["style"] = ""

                # Replace the text content with SVG
                footnote_back.clear()
                svg = soup.new_tag("svg")
                svg["xmlns"] = "http://www.w3.org/2000/svg"
                svg["viewBox"] = "0 0 448 512"

                path = soup.new_tag("path")
                path["d"] = "M6.101 261.899L25.9 281.698c4.686 4.686 12.284 4.686 16.971 0L198 126.568V468c0 6.627 5.373 12 12 12h28c6.627 0 12-5.373 12-12V126.568l155.13 155.13c4.686 4.686 12.284 4.686 16.971 0l19.799-19.799c4.686-4.686 4.686-12.284 0-16.971L232.485 35.515c-4.686-4.686-12.284-4.686-16.971 0L6.101 244.929c-4.687 4.686-4.687 12.284 0 16.97z"

                svg.append(path)
                footnote_back.append(svg)

    return str(soup)


def footnote_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for footnote_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return footnote_enhancer(html, context)
