# engine/markdown/postprocessors/math_copy_button.py

import re
from bs4 import BeautifulSoup


def add_math_copy_buttons(html: str, context: dict) -> str:
    """
    Add copy buttons to display block math equations.

    Finds <span class="math display"> elements and adds a button bar with a copy button
    that allows copying the LaTeX source to clipboard.

    Pandoc with --mathjax outputs display math as:
    <span class="math display">
      \\[LaTeX source\\]
    </span>

    Or sometimes with a script tag:
    <span class="math display">
      <script type="math/tex; mode=display">LaTeX source</script>
    </span>
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find all display math spans - check for both possible class patterns
    math_spans = []

    # Pattern 1: <span class="math display">
    math_spans.extend(soup.find_all('span', class_='math display'))

    # Pattern 2: <span class="math" class="display"> (shouldn't happen but just in case)
    for span in soup.find_all('span', class_='math'):
        classes = span.get('class', [])
        if 'display' in classes and span not in math_spans:
            math_spans.append(span)

    for math_span in math_spans:
        # Check if button bar already exists
        if math_span.find('span', class_='block-button-bar'):
            continue

        # Extract LaTeX source from the math span
        latex_source = ""

        # Method 1: Check for script tag with type="math/tex"
        script_tag = math_span.find('script', type=lambda t: t and 'math/tex' in t)
        if script_tag:
            latex_source = script_tag.string or ""
        else:
            # Method 2: Get text content directly (Pandoc often outputs \[...\] or $$...$$)
            text_content = math_span.get_text()
            if text_content:
                # Remove \[ and \] delimiters if present
                latex_source = text_content.strip()
                if latex_source.startswith('\\[') and latex_source.endswith('\\]'):
                    latex_source = latex_source[2:-2].strip()
                elif latex_source.startswith('$$') and latex_source.endswith('$$'):
                    latex_source = latex_source[2:-2].strip()

        # If no LaTeX source found, skip this element
        if not latex_source:
            continue

        # Escape the LaTeX source for HTML attribute
        # Handle potential double-escaping from BeautifulSoup
        latex_escaped = (
            latex_source
            .replace('&', '&amp;')  # Must be first
            .replace('"', '&quot;')
            .replace("'", '&#x27;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )

        # Create the button bar HTML
        button_bar_html = f'''<span class="block-button-bar"><button type="button" class="copy" tabindex="-1" title="Copy LaTeX source of this equation to clipboard: {latex_escaped}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512"><path d="M433.941 65.941l-51.882-51.882A48 48 0 0 0 348.118 0H176c-26.51 0-48 21.49-48 48v48H48c-26.51 0-48 21.49-48 48v320c0 26.51 21.49 48 48 48h224c26.51 0 48-21.49 48-48v-48h80c26.51 0 48-21.49 48-48V99.882a48 48 0 0 0-14.059-33.941zM266 464H54a6 6 0 0 1-6-6V150a6 6 0 0 1 6-6h74v224c0 26.51 21.49 48 48 48h96v42a6 6 0 0 1-6 6zm128-96H182a6 6 0 0 1-6-6V54a6 6 0 0 1 6-6h106v88c0 13.255 10.745 24 24 24h88v202a6 6 0 0 1-6 6zm6-256h-64V48h9.632c1.591 0 3.117.632 4.243 1.757l48.368 48.368a6 6 0 0 1 1.757 4.243V112z"></path></svg></button><span class="scratchpad"></span></span>'''

        # Parse the button bar and insert it before the closing tag of math_span
        button_bar = BeautifulSoup(button_bar_html, 'html.parser')
        math_span.append(button_bar)

    return str(soup)


def math_copy_button_default(html: str, context: dict) -> str:
    """Default instance of math copy button postprocessor"""
    return add_math_copy_buttons(html, context)
