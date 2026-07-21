"""
Tests for the bibliography Tier-1 completion pass:

- Citation escaper no longer mangles email addresses
- Archived-file hash computation, deduplication, and format validation
  (now on the SourceFile model — see also test_source_files.py)
- Proactive Wayback archival (signal + task)
- Archive-URL preference for broken sources
- Per-post annotations rendered in the bibliography
- Source search vector population + search integration
"""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from engine.admin.post import PostCitationInline
from engine.bibliography.renderer import render_bibliography_section
from engine.markdown.postprocessors.citation_renderer import (
    _csl_item,
    citation_renderer,
)
from engine.markdown.preprocessors.citation_escaper import escape_citations
from engine.models import Post, PostCitation, Source, SourceFile
from engine.search.service import build_search_results, search_sources

User = get_user_model()


class CitationEscaperEmailTests(TestCase):
    def test_email_address_is_not_escaped(self):
        text = "Contact me at user@example.com for details."
        self.assertEqual(escape_citations(text, {}), text)

    def test_narrative_citation_still_escaped(self):
        result = escape_citations("As @smith2024 argues.", {})
        self.assertIn("%%NCITE:smith2024%%", result)

    def test_bracketed_citation_still_escaped(self):
        result = escape_citations("Cited [@smith2024].", {})
        self.assertIn("%%CITE:smith2024%%", result)

    def test_backslash_escaped_at_is_untouched(self):
        text = r"Literal \@smith2024 stays."
        self.assertEqual(escape_citations(text, {}), text)


class ArchivedFileHashTests(TestCase):
    def _file(self, key, content=b"%PDF-1.4 fake pdf bytes", name="paper.pdf"):
        source = Source.objects.create(citation_key=key, title=f"Title for {key}")
        return SourceFile.objects.create(
            source=source,
            file=SimpleUploadedFile(name, content),
        )

    def test_hash_computed_on_upload(self):
        source_file = self._file("hash2024a")
        self.assertEqual(len(source_file.sha256), 64)

    def test_duplicate_content_reuses_stored_file(self):
        first = self._file("dupe2024a")
        second = self._file("dupe2024b")
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.file.name, second.file.name)

    def test_different_content_stored_separately(self):
        first = self._file("uniq2024a")
        second = self._file("uniq2024b", content=b"%PDF-1.4 other bytes entirely")
        self.assertNotEqual(first.sha256, second.sha256)
        self.assertNotEqual(first.file.name, second.file.name)

    def test_disallowed_extension_rejected(self):
        source = Source.objects.create(citation_key="badext2024", title="Bad ext")
        source_file = SourceFile(
            source=source,
            file=SimpleUploadedFile("malware.exe", b"MZ"),
        )
        with self.assertRaises(ValidationError):
            source_file.full_clean()

    def test_docx_extension_accepted(self):
        source = Source.objects.create(citation_key="docx2024", title="A manuscript")
        source_file = SourceFile(
            source=source,
            file=SimpleUploadedFile("manuscript.docx", b"PK\x03\x04 docx bytes"),
        )
        source_file.full_clean()  # Should not raise


@override_settings(WAYBACK_AUTO_SUBMIT=True)
class WaybackSignalTests(TestCase):
    @patch("engine.bibliography.tasks.archive_source_url")
    def test_create_with_url_enqueues_archival(self, mock_task):
        Source.objects.create(
            citation_key="way2024a",
            title="Web source",
            url="https://example.com/article",
        )
        mock_task.delay.assert_called_once()

    @patch("engine.bibliography.tasks.archive_source_url")
    def test_create_without_url_does_not_enqueue(self, mock_task):
        Source.objects.create(citation_key="way2024b", title="No URL")
        mock_task.delay.assert_not_called()

    @patch("engine.bibliography.tasks.archive_source_url")
    def test_unrelated_save_does_not_enqueue(self, mock_task):
        source = Source.objects.create(
            citation_key="way2024c",
            title="Web source",
            url="https://example.com/article",
        )
        mock_task.reset_mock()
        source.note = "updated note"
        source.save()
        mock_task.delay.assert_not_called()

    @patch("engine.bibliography.tasks.archive_source_url")
    def test_url_change_enqueues_archival(self, mock_task):
        source = Source.objects.create(
            citation_key="way2024d",
            title="Web source",
            url="https://example.com/article",
        )
        mock_task.reset_mock()
        source.url = "https://example.com/moved"
        source.save()
        mock_task.delay.assert_called_once()


class WaybackTaskTests(TestCase):
    @patch("engine.bibliography.link_checker.check_wayback_machine")
    @patch("engine.bibliography.link_checker.submit_to_wayback")
    def test_task_submits_and_backfills_archive_url(self, mock_submit, mock_check):
        from engine.bibliography.tasks import archive_source_url

        mock_submit.return_value = True
        mock_check.return_value = "https://web.archive.org/web/2026/example"
        source = Source.objects.create(
            citation_key="waytask2024",
            title="Web source",
            url="https://example.com/article",
        )
        result = archive_source_url.apply(args=[source.pk]).get()
        self.assertTrue(result["success"])
        mock_submit.assert_called_once_with("https://example.com/article")
        source.refresh_from_db()
        self.assertEqual(source.url_archive, "https://web.archive.org/web/2026/example")


class ArchiveUrlPreferenceTests(TestCase):
    def _source(self, status):
        return Source.objects.create(
            citation_key=f"pref{status}2024",
            title="Rotting link",
            url="https://example.com/dead",
            url_status=status,
            url_archive="https://web.archive.org/web/2026/dead",
        )

    def test_broken_source_uses_archive_url(self):
        item = _csl_item(self._source("broken"))
        self.assertEqual(item["URL"], "https://web.archive.org/web/2026/dead")

    def test_ok_source_keeps_primary_url(self):
        item = _csl_item(self._source("ok"))
        self.assertEqual(item["URL"], "https://example.com/dead")

    def test_swap_does_not_mutate_stored_csl_json(self):
        source = self._source("archived")
        _csl_item(source)
        self.assertEqual(source.csl_json["URL"], "https://example.com/dead")


class BibliographyRenderingTests(TestCase):
    def test_annotation_rendered_and_escaped(self):
        html = render_bibliography_section(
            entries=[("smith2024", "<div class='csl-entry'>Smith 2024</div>")],
            annotations={"smith2024": "Key <study> on the topic"},
        )
        self.assertIn("reference-annotation", html)
        self.assertIn("Key &lt;study&gt; on the topic", html)

    def test_no_annotation_no_div(self):
        html = render_bibliography_section(
            entries=[("smith2024", "<div class='csl-entry'>Smith 2024</div>")],
        )
        self.assertNotIn("reference-annotation", html)

    def test_file_link_label_matches_extension(self):
        html = render_bibliography_section(
            entries=[
                ("pdfkey", "<div class='csl-entry'>A</div>"),
                ("dockey", "<div class='csl-entry'>B</div>"),
            ],
            source_files={
                "pdfkey": ["/media/sources/2026/07/paper.pdf"],
                "dockey": ["/media/sources/2026/07/manuscript.docx"],
            },
        )
        self.assertIn("[PDF]", html)
        self.assertIn("[DOC]", html)


class CitationRendererAnnotationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="author", password="x")
        cls.source = Source.objects.create(
            citation_key="anno2024",
            title="Annotated Source",
            authors=[{"family": "Smith", "given": "Jo"}],
            issued_date={"date-parts": [[2024]]},
        )
        cls.post = Post.objects.create(
            title="Annotated Post",
            slug="annotated-post",
            author=cls.user,
            content_markdown="Cited [@anno2024].",
        )
        PostCitation.objects.create(
            post=cls.post,
            source=cls.source,
            position=0,
            annotation="Why this source matters here.",
        )

    def test_annotation_appears_in_rendered_bibliography(self):
        html = citation_renderer("<p>Cited %%CITE:anno2024%%</p>", {"post": self.post})
        self.assertIn('id="references"', html)
        self.assertIn("Why this source matters here.", html)

    def test_no_post_in_context_renders_without_annotations(self):
        html = citation_renderer("<p>Cited %%CITE:anno2024%%</p>", {})
        self.assertIn('id="references"', html)
        self.assertNotIn("Why this source matters here.", html)


class PostCitationInlineTests(TestCase):
    def test_annotation_is_editable_but_rows_are_managed(self):
        inline = PostCitationInline(PostCitation, AdminSite())
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            username="admin", password="x", email="a@example.com"
        )
        self.assertTrue(inline.has_change_permission(request))
        self.assertFalse(inline.has_add_permission(request))
        self.assertFalse(inline.has_delete_permission(request))


class SourceSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="author", password="x", is_staff=True
        )
        cls.public_source = Source.objects.create(
            citation_key="quantum2024",
            title="Quantum Entanglement Studies",
            authors=[{"family": "Bell", "given": "J"}],
        )
        cls.draft_source = Source.objects.create(
            citation_key="hidden2024",
            title="Quantum Draft-Only Findings",
        )
        cls.published_post = Post.objects.create(
            title="Published Post",
            slug="published-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="Cited [@quantum2024].",
        )
        cls.draft_post = Post.objects.create(
            title="Draft Post",
            slug="draft-post",
            author=cls.user,
            content_markdown="Cited [@hidden2024].",
        )
        PostCitation.objects.create(
            post=cls.published_post, source=cls.public_source, position=0
        )
        PostCitation.objects.create(
            post=cls.draft_post, source=cls.draft_source, position=0
        )

    def test_search_vector_populated_on_save(self):
        self.public_source.refresh_from_db()
        self.assertIsNotNone(self.public_source.search_vector)

    def test_anonymous_sees_only_publicly_cited_sources(self):
        keys = {s.citation_key for s in search_sources("Quantum")}
        self.assertIn("quantum2024", keys)
        self.assertNotIn("hidden2024", keys)

    def test_staff_sees_sources_cited_in_drafts(self):
        keys = {s.citation_key for s in search_sources("Quantum", user=self.user)}
        self.assertIn("hidden2024", keys)

    def test_uncited_sources_never_surface(self):
        Source.objects.create(citation_key="uncited2024", title="Quantum But Uncited")
        keys = {s.citation_key for s in search_sources("Quantum", user=self.user)}
        self.assertNotIn("uncited2024", keys)

    def test_build_search_results_links_to_reference_anchor(self):
        results = build_search_results("Quantum")
        sources = results["results"]["sources"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["citation_key"], "quantum2024")
        self.assertEqual(
            sources[0]["url"],
            f"{self.published_post.get_absolute_url()}#ref-quantum2024",
        )
        self.assertEqual(sources[0]["cited_count"], 1)

    def test_rebuild_search_vectors_covers_sources(self):
        from engine.tasks import rebuild_search_vectors

        result = rebuild_search_vectors.apply().get()
        self.assertGreaterEqual(result["sources_updated"], 2)
