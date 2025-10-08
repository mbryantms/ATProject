from bs4 import BeautifulSoup
from django.utils.text import slugify


def extract_toc_from_html(html: str) -> list[dict]:
    """
    Given rendered HTML, return a list of headings for a TOC.
    Each entry has: level, id, title.
    """
    soup = BeautifulSoup(html, "html.parser")
    toc = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = heading.get_text(strip=True)
        level = int(heading.name[1])  # "h2" -> 2
        hid = heading.get("id") or slugify(text)
        toc.append({"level": level, "id": hid, "title": text})
    return toc
