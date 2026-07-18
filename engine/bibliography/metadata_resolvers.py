"""
Metadata resolution from DOI, ISBN, and URL sources.

Provides auto-population of Source fields by fetching metadata from:
- DOI: CrossRef API (returns CSL-JSON natively)
- ISBN: Open Library API
- URL: OpenGraph, Dublin Core, Schema.org JSON-LD, HTML meta tags
"""

import json
import logging
import re
from urllib.parse import urlparse
from urllib.request import Request

from .net import safe_urlopen

logger = logging.getLogger(__name__)

_USER_AGENT = "ATProject/1.0 (Bibliography System; mailto:admin@example.com)"
_TIMEOUT = 15


def resolve_doi(doi: str) -> dict | None:
    """
    Fetch metadata from CrossRef for a DOI.

    CrossRef returns CSL-JSON natively, making this the ideal metadata source.

    Returns:
        CSL-JSON dict, or None on failure.
    """
    doi = doi.strip()
    # Normalize: remove URL prefix if present
    doi = re.sub(r"^https?://doi\.org/", "", doi)
    doi = re.sub(r"^doi:", "", doi, flags=re.IGNORECASE)

    if not doi:
        return None

    url = f"https://api.crossref.org/works/{doi}"
    req = Request(url, headers={"User-Agent": _USER_AGENT})

    try:
        with safe_urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())

        message = data.get("message", {})

        # Map CrossRef response to CSL-JSON
        csl = {
            "type": _crossref_type_to_csl(message.get("type", "")),
            "title": _first_or_empty(message.get("title", [])),
            "DOI": message.get("DOI", doi),
        }

        # Authors
        authors = []
        for author in message.get("author", []):
            a = {}
            if "family" in author:
                a["family"] = author["family"]
            if "given" in author:
                a["given"] = author["given"]
            if "name" in author and not a:
                a["literal"] = author["name"]
            if a:
                authors.append(a)
        if authors:
            csl["author"] = authors

        # Container
        container = _first_or_empty(message.get("container-title", []))
        if container:
            csl["container-title"] = container

        # Publisher
        if message.get("publisher"):
            csl["publisher"] = message["publisher"]

        # Volume, issue, page
        if message.get("volume"):
            csl["volume"] = message["volume"]
        if message.get("issue"):
            csl["issue"] = message["issue"]
        if message.get("page"):
            csl["page"] = message["page"]

        # Date
        issued = message.get("issued", {}).get("date-parts")
        if issued:
            csl["issued"] = {"date-parts": issued}

        # URL
        if message.get("URL"):
            csl["URL"] = message["URL"]

        # ISSN/ISBN
        issn_list = message.get("ISSN", [])
        if issn_list:
            csl["ISSN"] = issn_list[0]
        isbn_list = message.get("ISBN", [])
        if isbn_list:
            csl["ISBN"] = isbn_list[0]

        # Abstract
        if message.get("abstract"):
            # CrossRef abstracts sometimes have JATS XML tags
            abstract = re.sub(r"<[^>]+>", "", message["abstract"])
            csl["abstract"] = abstract.strip()

        return csl

    except Exception:
        logger.exception("Failed to resolve DOI: %s", doi)
        return None


def resolve_isbn(isbn: str) -> dict | None:
    """
    Fetch metadata from Open Library for an ISBN.

    Returns:
        CSL-JSON dict, or None on failure.
    """
    isbn = re.sub(r"[\s-]", "", isbn)
    if not isbn:
        return None

    url = f"https://openlibrary.org/isbn/{isbn}.json"
    req = Request(url, headers={"User-Agent": _USER_AGENT})

    try:
        with safe_urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())

        csl = {
            "type": "book",
            "title": data.get("title", ""),
            "ISBN": isbn,
        }

        # Publisher
        if data.get("publishers"):
            csl["publisher"] = data["publishers"][0]

        # Date
        if data.get("publish_date"):
            year_match = re.search(r"\d{4}", data["publish_date"])
            if year_match:
                csl["issued"] = {"date-parts": [[int(year_match.group())]]}

        # Pages
        if data.get("number_of_pages"):
            csl["number-of-pages"] = str(data["number_of_pages"])

        # Authors (requires additional API call to resolve author keys)
        authors = []
        for author_ref in data.get("authors", []):
            author_key = author_ref.get("key", "")
            if author_key:
                try:
                    author_url = f"https://openlibrary.org{author_key}.json"
                    author_req = Request(
                        author_url, headers={"User-Agent": _USER_AGENT}
                    )
                    with safe_urlopen(author_req, timeout=_TIMEOUT) as aresp:
                        author_data = json.loads(aresp.read())
                    name = author_data.get("name", "")
                    if name:
                        parts = name.rsplit(" ", 1)
                        if len(parts) == 2:
                            authors.append({"given": parts[0], "family": parts[1]})
                        else:
                            authors.append({"literal": name})
                except Exception:
                    pass
        if authors:
            csl["author"] = authors

        return csl

    except Exception:
        logger.exception("Failed to resolve ISBN: %s", isbn)
        return None


def resolve_url(url: str) -> dict | None:
    """
    Extract metadata from a web page URL using OpenGraph, meta tags, etc.

    Returns:
        CSL-JSON dict, or None on failure.
    """
    if not url:
        return None

    req = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html",
        },
    )

    try:
        with safe_urlopen(req, timeout=_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        csl = {
            "type": "webpage",
            "URL": url,
        }

        # OpenGraph
        og_title = _meta_content(soup, property="og:title")
        og_site = _meta_content(soup, property="og:site_name")
        og_desc = _meta_content(soup, property="og:description")
        og_type = _meta_content(soup, property="og:type")

        # Standard meta
        title = og_title or (soup.title.string if soup.title else "")
        description = og_desc or _meta_content(soup, name="description")
        author = _meta_content(soup, name="author")
        published = (
            _meta_content(soup, property="article:published_time")
            or _meta_content(soup, name="date")
            or _meta_content(soup, name="DC.date")
        )

        if title:
            csl["title"] = title.strip()
        if og_site:
            csl["container-title"] = og_site
        if description:
            csl["abstract"] = description.strip()

        # Author
        if author:
            parts = author.strip().rsplit(" ", 1)
            if len(parts) == 2:
                csl["author"] = [{"given": parts[0], "family": parts[1]}]
            else:
                csl["author"] = [{"literal": author.strip()}]

        # Date
        if published:
            year_match = re.search(r"(\d{4})", published)
            if year_match:
                date_parts = [int(year_match.group(1))]
                month_match = re.search(r"\d{4}-(\d{2})", published)
                if month_match:
                    date_parts.append(int(month_match.group(1)))
                    day_match = re.search(r"\d{4}-\d{2}-(\d{2})", published)
                    if day_match:
                        date_parts.append(int(day_match.group(1)))
                csl["issued"] = {"date-parts": [date_parts]}

        # Accessed date
        from datetime import date as date_cls

        today = date_cls.today()
        csl["accessed"] = {"date-parts": [[today.year, today.month, today.day]]}

        # Domain-specific type mapping
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if "arxiv.org" in domain:
            csl["type"] = "article"
        elif "youtube.com" in domain or "youtu.be" in domain:
            csl["type"] = "motion_picture"
        elif "github.com" in domain:
            csl["type"] = "software"
        elif og_type == "article":
            csl["type"] = "article"
            if not og_site:
                csl["type"] = "post-weblog"

        return csl

    except Exception:
        logger.exception("Failed to resolve URL: %s", url)
        return None


def apply_metadata_to_source(source, csl_data: dict) -> list[str]:
    """
    Apply resolved metadata to a Source, only filling empty fields.

    Returns:
        List of field names that were updated.
    """
    updated = []
    field_map = {
        "title": "title",
        "type": "source_type",
        "author": "authors",
        "editor": "editors",
        "translator": "translators",
        "container-title": "container_title",
        "publisher": "publisher",
        "publisher-place": "publisher_place",
        "volume": "volume",
        "issue": "issue",
        "page": "page",
        "edition": "edition",
        "issued": "issued_date",
        "accessed": "accessed_date",
        "DOI": "doi",
        "ISBN": "isbn",
        "ISSN": "issn",
        "URL": "url",
        "abstract": "abstract",
        "language": "language",
    }

    for csl_field, model_field in field_map.items():
        value = csl_data.get(csl_field)
        if not value:
            continue

        current = getattr(source, model_field, None)
        # Only fill empty fields
        if current in (None, "", [], {}):
            setattr(source, model_field, value)
            updated.append(model_field)

    return updated


def _meta_content(soup, **kwargs) -> str:
    """Extract content from a <meta> tag."""
    tag = soup.find("meta", attrs=kwargs)
    if tag:
        return tag.get("content", "")
    return ""


def _first_or_empty(lst: list) -> str:
    """Return the first element of a list, or empty string."""
    return lst[0] if lst else ""


def _crossref_type_to_csl(crossref_type: str) -> str:
    """Map CrossRef work type to CSL type."""
    mapping = {
        "journal-article": "article-journal",
        "book": "book",
        "book-chapter": "chapter",
        "proceedings-article": "paper-conference",
        "dataset": "dataset",
        "report": "report",
        "standard": "standard",
        "monograph": "book",
        "edited-book": "book",
        "reference-book": "book",
        "dissertation": "thesis",
        "posted-content": "article",
    }
    return mapping.get(crossref_type, "article")
