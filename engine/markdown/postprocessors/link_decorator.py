# engine/markdown/postprocessors/link_decorator.py
"""
Postprocessor that decorates links with data attributes for icon styling.

This postprocessor adds data-link-icon and data-link-icon-type attributes to
links based on their URL patterns and file extensions. These attributes are
used by CSS to display appropriate icons next to links.

Expected usage:
    <a href="https://example.com/file.pdf">Document</a>

Becomes:
    <a href="https://example.com/file.pdf" data-link-icon="pdf" data-link-icon-type="svg">Document</a>

The CSS in link-icons.css uses these attributes to display icons.
"""

from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse


def link_decorator(html: str, context: dict) -> str:
    """
    Decorate links with data attributes for icon styling.

    Processes all <a> elements and adds data-link-icon and data-link-icon-type
    attributes based on URL patterns and file extensions.

    Args:
        html: HTML string to process
        context: Context dictionary (unused but required for postprocessor signature)

    Returns:
        Processed HTML with decorated links
    """
    soup = BeautifulSoup(html, "html.parser")

    # File type definitions (icon_name, icon_type, extensions)
    # Extensions should be space-separated
    file_link_types = [
        # Textfiles
        ["txt", "svg", "opml txt xml json jsonl md"],
        # Code, scripts, etc.
        ["code", "svg", "css hs js conf sh r patch diff"],
        # Word (& compatible) documents
        ["worddoc", "svg", "doc docx"],
        # Excel (& compatible) documents
        ["spreadsheet", "svg", "xls xlsx ods"],
        # CSV files
        ["csv", "svg", "csv"],
        # Images
        ["image", "svg", "gif bmp ico jpg jpeg png svg xcf"],
        # Audio files
        ["audio", "svg", "mp3 wav flac ogg rm"],
        # Video files
        ["file-video", "svg", "swf mp4 mkv webm"],
        # Archive files
        ["archive", "svg", "tar zip xz img bin pkl onnx pt"],
        # Miscellaneous files
        ["misc", "svg", "ebt mdb mht ttf"],
        # EPUB files
        ["EPUB", "text,sans,quad", "epub"],
    ]

    # Domain/target definitions (icon_name, icon_type, pattern)
    # Pattern can be string (exact match) or regex pattern string
    target_link_types = [
        # Academic/Research
        ["𝛘", "text", r"arxiv\.org$"],  # ArXiv
        ["google-scholar", "svg", r"scholar\.google\.com$"],
        ["nlm-ncbi", "svg", r"nlm\.nih\.gov$"],  # PubMed/NCBI
        ["plos", "svg", r"plos\.org$"],
        ["chi-dna", "svg", r"biorxiv\.org$"],
        ["chi-dna", "svg", r"medrxiv\.org$"],

        # Tech/Code
        ["github", "svg", r"github\.com$"],
        ["stack-exchange", "svg", r"stackoverflow\.com$"],
        ["stack-exchange", "svg", r"stackexchange\.com$"],

        # Social/Community
        ["reddit", "svg", r"reddit\.com$"],
        ["twitter", "svg", r"x\.com$"],
        ["youtube", "svg", r"youtube\.com$"],
        ["youtube", "svg", r"youtu\.be$"],

        # News/Media
        ["wikipedia", "svg", r"wikipedia\.org$"],
        ["wikipedia", "svg", r"wikimedia\.org$"],
        ["wikipedia", "svg", r"wiktionary\.org$"],
        ["new-york-times", "svg", r"nytimes\.com$"],
        ["the-guardian", "svg", r"theguardian\.com$"],
        ["wired", "svg", r"wired\.com$"],

        # Other
        ["internet-archive", "svg", r"archive\.org$"],
        ["internet-archive", "svg", r"waybackmachine\.org$"],
        ["amazon", "svg", r"amazon\.com$"],
    ]

    for link in soup.find_all("a"):
        # Skip links with .icon-not class
        if "icon-not" in link.get("class", []):
            continue

        # Skip links that already have icon attributes
        if link.get("data-link-icon"):
            continue

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

        # Check file types first (by extension)
        icon_assigned = False
        for icon_name, icon_type, extensions in file_link_types:
            ext_list = extensions.split()
            for ext in ext_list:
                if path.endswith(f".{ext}"):
                    link["data-link-icon"] = icon_name
                    link["data-link-icon-type"] = icon_type
                    icon_assigned = True
                    break
            if icon_assigned:
                break

        # If no file type match, check domain patterns
        if not icon_assigned and hostname:
            for icon_name, icon_type, pattern in target_link_types:
                try:
                    if re.search(pattern, hostname, re.IGNORECASE):
                        link["data-link-icon"] = icon_name
                        link["data-link-icon-type"] = icon_type
                        break
                except re.error:
                    # Skip invalid regex patterns
                    continue

    return str(soup)


def link_decorator_default(html: str, context: dict) -> str:
    """
    Default configuration for link_decorator.

    This is the function that should be registered in POSTPROCESSORS.
    """
    return link_decorator(html, context)
