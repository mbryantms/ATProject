# engine/markdown/postprocessors/link_decorator.py
"""
Unified link postprocessor that handles all link enhancements.

This postprocessor:
1. Adds target="_blank" and rel="noopener noreferrer" to external links
2. Adds "external-link" class to external links
3. Adds data-link-icon and data-link-icon-type attributes for icon styling

Consolidates the functionality of:
- link_decorator.py (icon decoration)
- modify_external_links.py (external link attributes)

Uses shared soup caching for efficiency.
"""

import re
from urllib.parse import urlparse

from .utils import get_shared_soup, soup_to_html

# File type definitions: (icon_name, icon_type, space-separated extensions)
FILE_LINK_TYPES = [
    # Textfiles
    ("txt", "svg", "opml txt xml json jsonl md"),
    # Code, scripts, etc.
    ("code", "svg", "css hs js conf sh r patch diff"),
    # Word (& compatible) documents
    ("worddoc", "svg", "doc docx"),
    # Excel (& compatible) documents
    ("spreadsheet", "svg", "xls xlsx ods"),
    # CSV files
    ("csv", "svg", "csv"),
    # Images
    ("image", "svg", "gif bmp ico jpg jpeg png svg xcf"),
    # Audio files
    ("audio", "svg", "mp3 wav flac ogg rm"),
    # Video files
    ("file-video", "svg", "swf mp4 mkv webm"),
    # Archive files
    ("archive", "svg", "tar zip xz img bin pkl onnx pt"),
    # Miscellaneous files
    ("misc", "svg", "ebt mdb mht ttf"),
    # EPUB files
    ("EPUB", "text,sans,quad", "epub"),
    # PDF files
    ("pdf", "svg", "pdf"),
]

# Domain/target definitions: (icon_name, icon_type, regex pattern for hostname)
TARGET_LINK_TYPES = [
    # Academic/Research
    ("𝛘", "text", r"arxiv\.org$"),  # ArXiv
    ("google-scholar", "svg", r"scholar\.google\.com$"),
    ("nlm-ncbi", "svg", r"nlm\.nih\.gov$"),  # PubMed/NCBI
    ("plos", "svg", r"plos\.org$"),
    ("chi-dna", "svg", r"biorxiv\.org$"),
    ("chi-dna", "svg", r"medrxiv\.org$"),
    # Tech/Code
    ("github", "svg", r"github\.com$"),
    ("stack-exchange", "svg", r"stackoverflow\.com$"),
    ("stack-exchange", "svg", r"stackexchange\.com$"),
    # Social/Community
    ("reddit", "svg", r"reddit\.com$"),
    ("twitter", "svg", r"x\.com$"),
    ("youtube", "svg", r"youtube\.com$"),
    ("youtube", "svg", r"youtu\.be$"),
    # News/Media
    ("wikipedia", "svg", r"wikipedia\.org$"),
    ("wikipedia", "svg", r"wikimedia\.org$"),
    ("wikipedia", "svg", r"wiktionary\.org$"),
    ("new-york-times", "svg", r"nytimes\.com$"),
    ("the-guardian", "svg", r"theguardian\.com$"),
    ("wired", "svg", r"wired\.com$"),
    # Other
    ("internet-archive", "svg", r"archive\.org$"),
    ("internet-archive", "svg", r"waybackmachine\.org$"),
    ("amazon", "svg", r"amazon\.com$"),
]

# Internal domains - links to these won't be marked as external
# Add your own domain(s) here
INTERNAL_DOMAINS = set()


def _is_external_link(href: str, hostname: str) -> bool:
    """Check if a link is external (not internal to the site)."""
    if not href:
        return False

    # Must start with http:// or https://
    if not href.startswith(("http://", "https://")):
        return False

    # Check against internal domains
    if hostname and hostname in INTERNAL_DOMAINS:
        return False

    return True


def _get_file_icon(path: str) -> tuple[str, str] | None:
    """Get icon name and type for a file extension."""
    path_lower = path.lower()
    for icon_name, icon_type, extensions in FILE_LINK_TYPES:
        for ext in extensions.split():
            if path_lower.endswith(f".{ext}"):
                return icon_name, icon_type
    return None


def _get_domain_icon(hostname: str) -> tuple[str, str] | None:
    """Get icon name and type for a domain."""
    if not hostname:
        return None

    for icon_name, icon_type, pattern in TARGET_LINK_TYPES:
        try:
            if re.search(pattern, hostname, re.IGNORECASE):
                return icon_name, icon_type
        except re.error:
            continue
    return None


def link_decorator(html: str, context: dict) -> str:
    """
    Unified link decorator that handles:
    1. External link attributes (target="_blank", rel, class)
    2. Icon data attributes for CSS styling

    Uses shared soup caching for efficiency when multiple postprocessors
    need to parse the same HTML.

    Args:
        html: HTML string to process
        context: Context dictionary for shared soup caching

    Returns:
        Processed HTML with decorated links
    """
    soup = get_shared_soup(html, context)

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not href:
            continue

        # Parse URL
        try:
            parsed = urlparse(href)
            hostname = parsed.hostname or ""
            path = parsed.path.lower()
        except Exception:
            continue

        # --- External link handling ---
        if _is_external_link(href, hostname):
            # Add target="_blank" for external links
            link["target"] = "_blank"

            # Add security attributes
            link["rel"] = "noopener noreferrer"

            # Add external-link class
            existing_classes = link.get("class", [])
            if isinstance(existing_classes, str):
                existing_classes = existing_classes.split()
            if "external-link" not in existing_classes:
                existing_classes.append("external-link")
            link["class"] = existing_classes

        # --- Icon decoration ---
        # Skip links with .icon-not class
        if "icon-not" in link.get("class", []):
            continue

        # Skip links that already have icon attributes
        if link.get("data-link-icon"):
            continue

        # Check file types first (by extension)
        icon_info = _get_file_icon(path)
        if icon_info:
            link["data-link-icon"] = icon_info[0]
            link["data-link-icon-type"] = icon_info[1]
            continue

        # Check domain patterns
        icon_info = _get_domain_icon(hostname)
        if icon_info:
            link["data-link-icon"] = icon_info[0]
            link["data-link-icon-type"] = icon_info[1]

    return soup_to_html(context, soup)


def link_decorator_default(html: str, context: dict) -> str:
    """
    Default configuration for link_decorator.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return link_decorator(html, context)
