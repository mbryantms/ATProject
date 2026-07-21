"""
Tests for the Tier-4 public surface:

- BibTeX / RIS / CSL-JSON export converters and endpoints
- The public /library/ page (privacy, search, filters, metrics)
- The Further Reading section (model + postprocessor)
- Copy-citation buttons in the rendered bibliography
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from engine.bibliography.export import to_bibtex, to_csl_json, to_ris
from engine.bibliography.renderer import render_bibliography_section
from engine.markdown.postprocessors.further_reading import further_reading_renderer
from engine.models import Post, PostCitation, PostFurtherReading, Source

User = get_user_model()


def _make_post(author, slug, **kwargs):
    defaults = {
        "title": slug.replace("-", " ").title(),
        "slug": slug,
        "author": author,
        "status": Post.Status.PUBLISHED,
        "visibility": Post.Visibility.PUBLIC,
        "published_at": timezone.now(),
        "content_markdown": "Body.",
    }
    defaults.update(kwargs)
    return Post.objects.create(**defaults)


class ExportConverterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.article = Source.objects.create(
            citation_key="vaughan2025deep",
            title="Deep Climate Signals",
            source_type="article-journal",
            authors=[{"family": "Vaughan", "given": "Ada"}],
            container_title="Nature Climate",
            issued_date={"date-parts": [[2025]]},
            volume="12",
            issue="3",
            page="100-115",
            doi="10.1000/xyz123",
        )
        cls.book = Source.objects.create(
            citation_key="orglit2020",
            title="Standards & Practice",
            source_type="book",
            authors=[{"literal": "ISO Working Group"}],
            publisher="ISO Press",
        )

    def test_bibtex_article(self):
        bib = to_bibtex([self.article])
        self.assertIn("@article{vaughan2025deep,", bib)
        self.assertIn("author = {Vaughan, Ada}", bib)
        self.assertIn("journal = {Nature Climate}", bib)
        self.assertIn("pages = {100--115}", bib)
        self.assertIn("year = {2025}", bib)
        self.assertIn("doi = {10.1000/xyz123}", bib)

    def test_bibtex_escapes_specials_and_literal_names(self):
        bib = to_bibtex([self.book])
        self.assertIn("@book{orglit2020,", bib)
        self.assertIn(r"Standards \& Practice", bib)
        self.assertIn("author = {{ISO Working Group}}", bib)

    def test_ris_article(self):
        ris = to_ris([self.article])
        self.assertIn("TY  - JOUR", ris)
        self.assertIn("AU  - Vaughan, Ada", ris)
        self.assertIn("T2  - Nature Climate", ris)
        self.assertIn("SP  - 100", ris)
        self.assertIn("EP  - 115", ris)
        self.assertIn("ER  - ", ris)

    def test_csl_json_round_trips(self):
        data = json.loads(to_csl_json([self.article]))
        self.assertEqual(data[0]["id"], "vaughan2025deep")
        self.assertEqual(data[0]["container-title"], "Nature Climate")


class ExportEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="author", password="x", is_staff=True
        )
        cls.public_source = Source.objects.create(
            citation_key="pub2026", title="Public Source"
        )
        cls.draft_source = Source.objects.create(
            citation_key="draft2026", title="Draft-only Source"
        )
        cls.public_post = _make_post(cls.user, "public-post")
        cls.draft_post = _make_post(cls.user, "draft-post", status=Post.Status.DRAFT)
        PostCitation.objects.create(
            post=cls.public_post, source=cls.public_source, position=0
        )
        PostCitation.objects.create(
            post=cls.draft_post, source=cls.draft_source, position=0
        )

    def test_library_export_bibtex(self):
        response = self.client.get(reverse("library-export", kwargs={"fmt": "bib"}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        body = response.content.decode()
        self.assertIn("pub2026", body)
        self.assertNotIn("draft2026", body)

    def test_library_export_unknown_format_404(self):
        response = self.client.get(reverse("library-export", kwargs={"fmt": "docx"}))
        self.assertEqual(response.status_code, 404)

    def test_post_bibliography_export(self):
        response = self.client.get(
            reverse(
                "post-bibliography-export",
                kwargs={"slug": "public-post", "fmt": "ris"},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("ID  - pub2026", response.content.decode())

    def test_post_bibliography_export_draft_hidden_from_anonymous(self):
        response = self.client.get(
            reverse(
                "post-bibliography-export",
                kwargs={"slug": "draft-post", "fmt": "bib"},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_post_bibliography_export_draft_visible_to_staff(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "post-bibliography-export",
                kwargs={"slug": "draft-post", "fmt": "bib"},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("draft2026", response.content.decode())

    def test_post_without_citations_404(self):
        _make_post(self.user, "citeless-post")
        response = self.client.get(
            reverse(
                "post-bibliography-export",
                kwargs={"slug": "citeless-post", "fmt": "bib"},
            )
        )
        self.assertEqual(response.status_code, 404)


class LibraryPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="author", password="x", is_staff=True
        )
        cls.cited = Source.objects.create(
            citation_key="lib2026",
            title="Quantum Library Entry",
            source_type="article-journal",
            authors=[{"family": "Bell", "given": "J"}],
            issued_date={"date-parts": [[2024]]},
        )
        cls.book = Source.objects.create(
            citation_key="book2026",
            title="A Cited Book",
            source_type="book",
        )
        cls.uncited = Source.objects.create(
            citation_key="uncited2026", title="Never Cited"
        )
        cls.draft_only = Source.objects.create(
            citation_key="draftonly2026", title="Draft Cited Only"
        )
        cls.post = _make_post(cls.user, "citing-post")
        draft = _make_post(cls.user, "draft-post", status=Post.Status.DRAFT)
        PostCitation.objects.create(post=cls.post, source=cls.cited, position=0)
        PostCitation.objects.create(post=cls.post, source=cls.book, position=1)
        PostCitation.objects.create(post=draft, source=cls.draft_only, position=0)

    def test_library_lists_publicly_cited_only(self):
        response = self.client.get(reverse("library"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Quantum Library Entry", body)
        self.assertIn("A Cited Book", body)
        self.assertNotIn("Never Cited", body)
        self.assertNotIn("Draft Cited Only", body)

    def test_library_links_citing_post_anchor(self):
        body = self.client.get(reverse("library")).content.decode()
        self.assertIn(f"{self.post.get_absolute_url()}#ref-lib2026", body)

    def test_library_search_filter(self):
        body = self.client.get(reverse("library"), {"q": "Quantum"}).content.decode()
        self.assertIn("Quantum Library Entry", body)
        self.assertNotIn("A Cited Book", body)

    def test_library_author_search(self):
        body = self.client.get(reverse("library"), {"q": "Bell"}).content.decode()
        self.assertIn("Quantum Library Entry", body)

    def test_library_type_filter(self):
        body = self.client.get(reverse("library"), {"type": "book"}).content.decode()
        self.assertIn("A Cited Book", body)
        self.assertNotIn("Quantum Library Entry", body)

    def test_library_year_filter(self):
        body = self.client.get(reverse("library"), {"year": "2024"}).content.decode()
        self.assertIn("Quantum Library Entry", body)
        self.assertNotIn("A Cited Book", body)

    def test_export_links_present(self):
        body = self.client.get(reverse("library")).content.decode()
        self.assertIn("/library/export.bib", body)
        self.assertIn("/library/export.ris", body)
        self.assertIn("/library/export.json", body)


class FurtherReadingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="author", password="x")
        cls.post = _make_post(cls.user, "reading-post")
        cls.source = Source.objects.create(
            citation_key="fr2026",
            title="Recommended Reading",
            authors=[{"family": "Nguyen", "given": "Lan"}],
            issued_date={"date-parts": [[2023]]},
            url="https://example.com/reading",
        )
        PostFurtherReading.objects.create(
            post=cls.post,
            source=cls.source,
            position=0,
            note="Start here for background.",
        )

    def test_section_appended_without_citations(self):
        html = further_reading_renderer("<p>Body.</p>", {"post": self.post})
        self.assertIn('id="further-reading"', html)
        self.assertIn("Recommended Reading", html)
        self.assertIn("Start here for background.", html)
        self.assertIn("Nguyen", html)

    def test_section_inserted_after_references(self):
        base = (
            "<p>Body.</p>"
            '<section id="references" class="references">refs</section>'
            '<section id="footnotes">notes</section>'
        )
        html = further_reading_renderer(base, {"post": self.post})
        refs_end = html.find("</section>")
        fr_at = html.find('id="further-reading"')
        notes_at = html.find('id="footnotes"')
        self.assertGreater(fr_at, refs_end)
        self.assertLess(fr_at, notes_at)

    def test_archive_url_preferred_when_broken(self):
        self.source.url_status = "broken"
        self.source.url_archive = "https://web.archive.org/web/2026/reading"
        self.source.save()
        html = further_reading_renderer("<p>Body.</p>", {"post": self.post})
        self.assertIn("https://web.archive.org/web/2026/reading", html)
        self.assertNotIn('href="https://example.com/reading"', html)

    def test_no_entries_no_section(self):
        other = _make_post(self.user, "plain-post")
        html = further_reading_renderer("<p>Body.</p>", {"post": other})
        self.assertNotIn("further-reading", html)


class CopyButtonTests(TestCase):
    def test_copy_button_rendered_per_entry(self):
        html = render_bibliography_section(
            entries=[("smith2024", "<div class='csl-entry'>Smith 2024</div>")],
        )
        self.assertIn("copy-citation-button", html)
        self.assertIn('aria-label="Copy reference to clipboard"', html)
