"""
Text extraction from archived source files, for search indexing.

Extractors are deliberately forgiving: any failure yields an empty string
rather than an exception — a file that can't be text-extracted is still a
perfectly good archive.

Formats: PDF via pypdf, HTML via BeautifulSoup, DOCX via pandoc (pypandoc).
Legacy binary .doc is not extractable (pandoc can't read it) and yields "".
"""

import logging
import os
import tempfile
from io import BytesIO

logger = logging.getLogger(__name__)

# Cap stored text well below Postgres's 1MB tsvector limit; the search
# vector expression additionally caps the aggregate across files.
MAX_EXTRACT_CHARS = 200_000


def extract_text(file_field, extension: str) -> str:
    """
    Extract plain text from a stored file.

    Args:
        file_field: A Django FieldFile (opened from storage).
        extension: Lowercase file extension without the dot.

    Returns:
        Extracted text, truncated to MAX_EXTRACT_CHARS. Empty string when
        the format is unsupported or extraction fails.
    """
    try:
        file_field.seek(0)
        data = file_field.read()
        file_field.seek(0)
    except Exception:
        logger.warning("Could not read file %s for extraction", file_field.name)
        return ""

    if not data:
        return ""

    extractor = {
        "pdf": _extract_pdf,
        "html": _extract_html,
        "htm": _extract_html,
        "docx": _extract_docx,
    }.get(extension)
    if extractor is None:
        return ""

    try:
        text = extractor(data)
    except Exception:
        logger.warning("Text extraction failed for %s", file_field.name, exc_info=True)
        return ""

    return " ".join(text.split())[:MAX_EXTRACT_CHARS]


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
        if sum(len(p) for p in pages) > MAX_EXTRACT_CHARS:
            break
    return "\n".join(pages)


def _extract_html(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def _extract_docx(data: bytes) -> str:
    import pypandoc

    # pandoc needs a real file path for docx input
    fd, path = tempfile.mkstemp(suffix=".docx")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return pypandoc.convert_file(path, "plain", format="docx")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
