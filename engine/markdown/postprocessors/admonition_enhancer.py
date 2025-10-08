# engine/markdown/postprocessors/admonition_enhancer.py
"""
Postprocessor that enhances admonitions with proper structure.

Pandoc marks admonitions using fenced divs with classes like .admonition-tip,
.admonition-note, .admonition-warning, or .admonition-error.

Expected Pandoc markdown input:
    ::: {.admonition-tip}
    # Tip Title

    Content of the tip admonition.
    :::

Or without a title:
    ::: {.admonition-note}
    Content of the note admonition.
    :::

Pandoc HTML output:
    <div class="admonition-tip">
        <h1>Tip Title</h1>
        <p>Content of the tip admonition.</p>
    </div>

This postprocessor transforms it to:
    <div class="admonition tip block">
        <div class="admonition-title">
            <p class="first-graf">Tip Title</p>
        </div>
        <p class="first-graf">Content of the tip admonition.</p>
    </div>

Supported types: tip, note, warning, error
"""

from bs4 import BeautifulSoup


def admonition_enhancer(html: str, context: dict) -> str:
    """
    Enhance admonitions with proper structure and classes.

    Processes div.admonition-{type} containers and converts them into
    properly structured admonitions with type-specific classes.

    Args:
        html: HTML string to process
        context: Context dictionary (unused but required for postprocessor signature)

    Returns:
        Processed HTML with enhanced admonitions
    """
    soup = BeautifulSoup(html, "html.parser")

    # Supported admonition types
    admonition_types = ["tip", "note", "warning", "error"]

    for admonition_type in admonition_types:
        # Find all divs OR sections with class="admonition-{type}"
        # (sections may have been created by header_sectionizer)
        admonition_containers = soup.find_all(
            "div", class_=f"admonition-{admonition_type}"
        ) + soup.find_all("section", class_=f"admonition-{admonition_type}")

        for container in admonition_containers:
            # Convert section to div if needed
            if container.name == "section":
                container.name = "div"
            # Update container classes: remove admonition-{type}, add admonition, {type}, block
            if "class" in container.attrs:
                classes = container["class"]
                # Remove the original admonition-{type} class
                if f"admonition-{admonition_type}" in classes:
                    classes.remove(f"admonition-{admonition_type}")
                # Add new classes
                if "admonition" not in classes:
                    classes.insert(0, "admonition")
                if admonition_type not in classes:
                    classes.insert(1, admonition_type)
                if "block" not in classes:
                    classes.append("block")
            else:
                container["class"] = ["admonition", admonition_type, "block"]

            # Check if first child is a heading (h1-h6)
            first_child = None
            for child in container.children:
                if child.name:  # Skip text nodes
                    first_child = child
                    break

            if first_child and first_child.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                # Create admonition-title div
                title_div = soup.new_tag("div")
                title_div["class"] = ["admonition-title"]

                # Convert heading to paragraph
                title_p = soup.new_tag("p")
                title_p["class"] = ["first-graf"]

                # Move heading content to paragraph (excluding copy button)
                for content in list(first_child.contents):
                    # Skip copy-section-link-button if it exists
                    if hasattr(content, "name") and content.name == "button":
                        continue
                    title_p.append(content)

                title_div.append(title_p)

                # Replace heading with title div
                first_child.replace_with(title_div)

            # Process all paragraph elements in the admonition
            paragraphs = container.find_all("p", recursive=False)

            # Don't process paragraphs inside admonition-title
            title_div = container.find("div", class_="admonition-title")
            if title_div:
                title_paragraphs = title_div.find_all("p")
                paragraphs = [p for p in paragraphs if p not in title_paragraphs]

            for idx, p in enumerate(paragraphs):
                is_first = idx == 0

                # Ensure p has class attribute
                if "class" not in p.attrs:
                    p["class"] = []

                # Remove "block" class if it exists (may have been added by block_marker)
                if "block" in p["class"]:
                    p["class"].remove("block")

                # Add first-graf to first paragraph
                if is_first:
                    if "first-graf" not in p["class"]:
                        p["class"].insert(0, "first-graf")

    return str(soup)


def admonition_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for admonition_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return admonition_enhancer(html, context)
