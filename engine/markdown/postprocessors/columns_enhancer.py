# engine/markdown/postprocessors/columns_enhancer.py
"""
Postprocessor that enhances multi-column layouts.

Pandoc marks multi-column sections using fenced divs with class="columns".
This postprocessor processes these divs and ensures proper structure for CSS columns.

Expected Pandoc markdown input:
    ::: {.columns}
    - Item 1
    - Item 2
    - Item 3
    - Item 4
    :::

Or for figures:
    ::: {.columns .figures}
    - ![Image 1](img1.jpg)
    - ![Image 2](img2.jpg)
    :::

Pandoc HTML output:
    <div class="columns">
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
            <li>Item 4</li>
        </ul>
    </div>

This postprocessor adds necessary structural classes:
    <div class="columns">
        <ul class="list">
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
            <li>Item 4</li>
        </ul>
    </div>

For figures variant (.columns.figures), lists are processed appropriately.
"""

from bs4 import BeautifulSoup


def columns_enhancer(html: str, context: dict) -> str:
    """
    Enhance multi-column layouts with proper classes.

    Processes div.columns containers and adds the "list" class to lists within them.

    Args:
        html: HTML string to process
        context: Context dictionary (unused but required for postprocessor signature)

    Returns:
        Processed HTML with enhanced columns
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find all div.columns elements
    columns_divs = soup.find_all("div", class_="columns")

    for div in columns_divs:
        # Find all lists (ul, ol) that are direct children
        lists = div.find_all(["ul", "ol"], recursive=False)

        for list_elem in lists:
            # Add "list" class to the list
            if "class" in list_elem.attrs:
                if "list" not in list_elem["class"]:
                    list_elem["class"].append("list")
            else:
                list_elem["class"] = ["list"]

    return str(soup)


def columns_enhancer_default(html: str, context: dict) -> str:
    """
    Default configuration for columns_enhancer.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return columns_enhancer(html, context)
