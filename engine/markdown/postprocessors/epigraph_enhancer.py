# engine/markdown/postprocessors/epigraph_enhancer.py
"""
Postprocessor that enhances epigraphs and text alignment divs.

EPIGRAPHS:
Pandoc marks epigraphs using a fenced div with class="epigraph" wrapping a blockquote.
This postprocessor finds those divs and restructures them into the proper epigraph format.

Expected Pandoc markdown input:
    ::: {.epigraph}
    > Text of epigraph
    >
    > --- Attribution
    :::

Pandoc HTML output:
    <div class="epigraph">
        <blockquote>
            <p>Text of epigraph</p>
            <p>--- Attribution</p>
        </blockquote>
    </div>

This postprocessor transforms it to:
    <div class="epigraph block">
        <blockquote class="first-block last-block blockquote-level-1 block">
            <p class="first-block first-graf block">Text of epigraph</p>
            <p class="last-block block">--- Attribution</p>
        </blockquote>
    </div>

TEXT ALIGNMENT:
Also processes fenced divs with .text-center or .text-right classes and applies
those classes to the content within (removing the wrapping div).

Expected Pandoc markdown input (single paragraph with line breaks):
    ::: {.text-center}
    Your humble & obedient servant,
    Gwern Branwen
    :::

Or multiple paragraphs (with blank lines):
    ::: {.text-center}
    First centered paragraph

    Second centered paragraph
    :::

Pandoc HTML output:
    <div class="text-center">
        <p>Your humble & obedient servant,<br>Gwern Branwen</p>
    </div>

This postprocessor transforms it to:
    <p class="text-center">Your humble & obedient servant,<br>Gwern Branwen</p>

Multiple paragraphs each get the class applied individually.
"""

from bs4 import BeautifulSoup


def epigraph_enhancer(html: str, context: dict) -> str:
    """
    Enhance epigraphs and text alignment divs.

    Processes:
    - div.epigraph containers that wrap blockquotes (from Pandoc fenced divs)
    - div.text-center and div.text-right containers (applies class to paragraphs)

    Args:
        html: HTML string to process
        context: Context dictionary (unused but required for postprocessor signature)

    Returns:
        Processed HTML with enhanced epigraphs and text alignment
    """
    soup = BeautifulSoup(html, "html.parser")

    # Process text alignment divs first
    for alignment_class in ["text-center", "text-right"]:
        alignment_divs = soup.find_all("div", class_=alignment_class)

        for div in alignment_divs:
            # Find all direct child paragraphs
            paragraphs = div.find_all("p", recursive=False)

            for p in paragraphs:
                # Add the alignment class to the paragraph
                if "class" in p.attrs:
                    if alignment_class not in p["class"]:
                        p["class"].append(alignment_class)
                else:
                    p["class"] = [alignment_class]

            # Unwrap the div, moving its contents to replace it
            div.unwrap()

    # Process epigraph divs
    epigraph_divs = soup.find_all("div", class_="epigraph")

    for div in epigraph_divs:
        # Add "block" class to the div
        if "class" in div.attrs:
            if "block" not in div["class"]:
                div["class"].append("block")
        else:
            div["class"] = ["epigraph", "block"]

        # Find the blockquote inside this div
        blockquote = div.find("blockquote", recursive=False)

        if not blockquote:
            continue

        # Update blockquote classes
        if "class" in blockquote.attrs:
            classes = blockquote["class"]
            # Add standard blockquote classes
            if "block" not in classes:
                classes.append("block")
            if "first-block" not in classes:
                classes.insert(0, "first-block")
            if "last-block" not in classes:
                classes.insert(1, "last-block")
        else:
            blockquote["class"] = ["first-block", "last-block", "block"]

        # Process paragraph elements inside blockquote
        paragraphs = blockquote.find_all("p", recursive=False)

        for idx, p in enumerate(paragraphs):
            is_first = idx == 0
            is_last = idx == len(paragraphs) - 1

            # Ensure p has class attribute
            if "class" not in p.attrs:
                p["class"] = []

            # Add block class
            # if "block" not in p["class"]:
            #     p["class"].append("block")

            # Add first-block and first-graf to first paragraph
            if is_first:
                if "first-block" not in p["class"]:
                    p["class"].insert(0, "first-block")
                if "first-graf" not in p["class"]:
                    p["class"].insert(1, "first-graf")

            # Add last-block to last paragraph
            if is_last:
                if "last-block" not in p["class"]:
                    p["class"].insert(0, "last-block")

    return str(soup)


def epigraph_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for epigraph_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return epigraph_enhancer(html, context)
