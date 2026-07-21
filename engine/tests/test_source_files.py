"""
Tests for the Tier-2 file archive build-out (SourceFile model):

- Kind auto-detection and magic-byte validation
- Multiple type-labeled file links in the bibliography, is_public gating
- Text extraction (task + helpers) feeding the Source search vector
- Zotero attachment download creating SourceFile rows
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from engine.bibliography.tasks import extract_source_file_text
from engine.bibliography.text_extraction import extract_text
from engine.bibliography.zotero_sync import _download_attachments
from engine.markdown.postprocessors.citation_renderer import citation_renderer
from engine.models import (
    Post,
    PostCitation,
    Source,
    SourceFile,
    SourceFileKind,
    SourceFileProvenance,
)
from engine.search.service import search_sources

User = get_user_model()

_HTML_DOC = b"<html><body><p>Entanglement thermodynamics results.</p></body></html>"


def _make_source(key, **kwargs):
    return Source.objects.create(citation_key=key, title=f"Title {key}", **kwargs)


def _attach(source, name, content, **kwargs):
    return SourceFile.objects.create(
        source=source, file=SimpleUploadedFile(name, content), **kwargs
    )


class SourceFileModelTests(TestCase):
    def test_kind_autodetected_from_extension(self):
        source = _make_source("kind2026")
        pdf = _attach(source, "a.pdf", b"%PDF-1.4 x")
        doc = _attach(source, "b.docx", b"PK\x03\x04 x")
        html = _attach(source, "c.html", _HTML_DOC)
        self.assertEqual(pdf.kind, SourceFileKind.PDF)
        self.assertEqual(doc.kind, SourceFileKind.DOC)
        self.assertEqual(html.kind, SourceFileKind.HTML)

    def test_metadata_captured_on_save(self):
        source = _make_source("meta2026")
        source_file = _attach(source, "paper.pdf", b"%PDF-1.4 hello")
        self.assertEqual(source_file.original_filename, "paper.pdf")
        self.assertEqual(source_file.size, len(b"%PDF-1.4 hello"))
        self.assertEqual(len(source_file.sha256), 64)

    def test_magic_byte_mismatch_rejected(self):
        source = _make_source("magic2026")
        source_file = SourceFile(
            source=source,
            file=SimpleUploadedFile("fake.pdf", b"MZ this is not a pdf"),
        )
        with self.assertRaises(ValidationError):
            source_file.full_clean()

    def test_html_lenient_magic_check(self):
        source = _make_source("magichtml2026")
        good = SourceFile(
            source=source, file=SimpleUploadedFile("snap.html", _HTML_DOC)
        )
        good.full_clean()  # Should not raise
        bad = SourceFile(
            source=source,
            file=SimpleUploadedFile("snap2.html", b"\x00\x01binary junk"),
        )
        with self.assertRaises(ValidationError):
            bad.full_clean()

    def test_dedup_reuses_file_across_sources(self):
        first = _attach(_make_source("da2026"), "one.pdf", b"%PDF-1.4 same")
        second = _attach(_make_source("db2026"), "two.pdf", b"%PDF-1.4 same")
        self.assertEqual(first.file.name, second.file.name)
        self.assertEqual(first.sha256, second.sha256)


class BibliographyFileLinksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = Source.objects.create(
            citation_key="files2026",
            title="Multi-file Source",
            authors=[{"family": "Smith", "given": "Jo"}],
            issued_date={"date-parts": [[2026]]},
        )
        _attach(cls.source, "manuscript.docx", b"PK\x03\x04 words")
        _attach(cls.source, "paper.pdf", b"%PDF-1.4 content")
        _attach(cls.source, "private-scan.pdf", b"%PDF-1.4 secret", is_public=False)

    def _render(self):
        return citation_renderer("<p>Cited %%CITE:files2026%%</p>", {})

    def test_multiple_labeled_links_rendered_pdf_first(self):
        html = self._render()
        self.assertIn("[PDF]", html)
        self.assertIn("[DOC]", html)
        self.assertLess(html.index("[PDF]"), html.index("[DOC]"))

    def test_private_files_not_linked(self):
        html = self._render()
        self.assertNotIn("private-scan", html)
        # Only the public PDF should produce a link.
        self.assertEqual(html.count("[PDF]"), 1)


class TextExtractionTests(TestCase):
    def test_extract_html_text(self):
        source_file = _attach(_make_source("xhtml2026"), "snap.html", _HTML_DOC)
        text = extract_text(source_file.file, "html")
        self.assertIn("Entanglement thermodynamics", text)

    def test_extract_unsupported_extension_returns_empty(self):
        source_file = _attach(_make_source("xdoc2026"), "old.doc", b"\xd0\xcf\x11\xe0")
        self.assertEqual(extract_text(source_file.file, "doc"), "")

    def test_extract_garbage_pdf_returns_empty(self):
        source_file = _attach(_make_source("xpdf2026"), "bad.pdf", b"%PDF-1.4 junk")
        self.assertEqual(extract_text(source_file.file, "pdf"), "")

    def test_extraction_task_populates_text_and_vector(self):
        source_file = _attach(_make_source("xtask2026"), "snap.html", _HTML_DOC)
        result = extract_source_file_text.apply(args=[source_file.pk]).get()
        self.assertTrue(result["success"])
        self.assertGreater(result["chars"], 0)
        source_file.refresh_from_db()
        self.assertIn("Entanglement thermodynamics", source_file.extracted_text)

    def test_search_finds_source_by_file_text(self):
        user = User.objects.create_user(username="author", password="x")
        source = _make_source("xsearch2026")
        source_file = _attach(source, "snap.html", _HTML_DOC)
        post = Post.objects.create(
            title="Citing Post",
            slug="citing-post",
            author=user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="Cited [@xsearch2026].",
        )
        PostCitation.objects.create(post=post, source=source, position=0)
        extract_source_file_text.apply(args=[source_file.pk]).get()

        keys = {s.citation_key for s in search_sources("thermodynamics")}
        self.assertIn("xsearch2026", keys)


class _FakeZotero:
    """Minimal stand-in for the pyzotero client's attachment API."""

    def __init__(self, children, files):
        self._children = children
        self._files = files

    def children(self, key):
        return self._children

    def file(self, key):
        return self._files[key]


class ZoteroAttachmentTests(TestCase):
    def test_download_creates_source_file_row(self):
        source = _make_source("zot2026", zotero_key="ZKEY1")
        zot = _FakeZotero(
            children=[
                {
                    "key": "ATT1",
                    "data": {
                        "itemType": "attachment",
                        "contentType": "application/pdf",
                        "filename": "paper.pdf",
                    },
                }
            ],
            files={"ATT1": b"%PDF-1.4 zotero bytes"},
        )
        stats = {"attachments_downloaded": 0}
        _download_attachments(zot, source, stats)

        self.assertEqual(stats["attachments_downloaded"], 1)
        source_file = source.files.get()
        self.assertEqual(source_file.provenance, SourceFileProvenance.ZOTERO)
        self.assertEqual(source_file.kind, SourceFileKind.PDF)
        self.assertEqual(source_file.original_filename, "paper.pdf")
        self.assertEqual(len(source_file.sha256), 64)

    def test_download_skipped_when_files_exist(self):
        source = _make_source("zot2026b", zotero_key="ZKEY2")
        _attach(source, "existing.pdf", b"%PDF-1.4 existing")
        stats = {"attachments_downloaded": 0}
        _download_attachments(_FakeZotero([], {}), source, stats)
        self.assertEqual(stats["attachments_downloaded"], 0)
        self.assertEqual(source.files.count(), 1)
