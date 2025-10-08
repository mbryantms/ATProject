# engine/markdown/postprocessors/add_heading_links.py

from bs4 import BeautifulSoup


def add_heading_copy_buttons(html: str, context: dict) -> str:
    """
    Add copy-section-link buttons to all headings (h1-h6).

    The button allows users to copy a direct link to that section.
    """
    soup = BeautifulSoup(html, "html.parser")

    # SVG for the link icon
    button_html = '''<button type="button" class="copy-section-link-button" title="Copy section link to clipboard" tabindex="-1"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512"><path d="M0 256C0 167.6 71.63 96 160 96H256C273.7 96 288 110.3 288 128C288 145.7 273.7 160 256 160H160C106.1 160 64 202.1 64 256C64 309 106.1 352 160 352H256C273.7 352 288 366.3 288 384C288 401.7 273.7 416 256 416H160C71.63 416 0 344.4 0 256zM480 416H384C366.3 416 352 401.7 352 384C352 366.3 366.3 352 384 352H480C533 352 576 309 576 256C576 202.1 533 160 480 160H384C366.3 160 352 145.7 352 128C352 110.3 366.3 96 384 96H480C568.4 96 640 167.6 640 256C640 344.4 568.4 416 480 416zM416 224C433.7 224 448 238.3 448 256C448 273.7 433.7 288 416 288H224C206.3 288 192 273.7 192 256C192 238.3 206.3 224 224 224H416z"></path></svg></button>'''

    # Find all heading tags (h1 through h6)
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        # Check if button already exists (avoid duplicates)
        if heading.find('button', class_='copy-section-link-button'):
            continue

        # Parse the button HTML and append to heading
        button = BeautifulSoup(button_html, 'html.parser')
        heading.append(button)

    return str(soup)