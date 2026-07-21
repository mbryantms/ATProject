"""
Tests for the Tier-3 authoring flow:

- Identifier classification (DOI / URL / ISBN / title)
- The create-source-from-editor endpoint behind the citation picker
- Per-object fetch-metadata / check-URL buttons on the Source change form
- Cited-in count and reverse post list on the Source admin
"""

import json
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from engine.admin.source import SourceAdmin
from engine.bibliography.metadata_resolvers import classify_identifier
from engine.models import Post, PostCitation, Source

User = get_user_model()

_CSL = {
    "type": "article-journal",
    "title": "Deep Climate Signals",
    "author": [{"family": "Vaughan", "given": "Ada"}],
    "container-title": "Nature Climate",
    "issued": {"date-parts": [[2025]]},
    "DOI": "10.1000/xyz123",
}


class ClassifyIdentifierTests(TestCase):
    def test_bare_doi(self):
        self.assertEqual(
            classify_identifier("10.1000/xyz123"), ("doi", "10.1000/xyz123")
        )

    def test_doi_resolver_url_stripped(self):
        self.assertEqual(
            classify_identifier("https://doi.org/10.1000/xyz123"),
            ("doi", "10.1000/xyz123"),
        )

    def test_doi_prefix_stripped(self):
        self.assertEqual(
            classify_identifier("doi:10.1000/xyz123"), ("doi", "10.1000/xyz123")
        )

    def test_url(self):
        self.assertEqual(
            classify_identifier("https://example.com/paper"),
            ("url", "https://example.com/paper"),
        )

    def test_isbn13_with_hyphens(self):
        self.assertEqual(
            classify_identifier("978-0-262-03384-8"), ("isbn", "9780262033848")
        )

    def test_isbn10_with_check_x(self):
        self.assertEqual(classify_identifier("155860832X"), ("isbn", "155860832X"))

    def test_title_fallback(self):
        self.assertEqual(
            classify_identifier("Thinking, Fast and Slow"),
            ("title", "Thinking, Fast and Slow"),
        )

    def test_empty(self):
        self.assertEqual(classify_identifier("   "), ("", ""))


class CreateSourceEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff", password="x", is_staff=True
        )

    def setUp(self):
        self.url = reverse("admin:engine_post_create_source")
        self.client.force_login(self.staff)

    def _post(self, identifier):
        return self.client.post(
            self.url,
            data=json.dumps({"identifier": identifier}),
            content_type="application/json",
        )

    def test_get_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.post(
            self.url, data="{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 302)

    def test_empty_identifier_rejected(self):
        response = self._post("")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Source.objects.count(), 0)

    def test_title_creates_bare_source(self):
        response = self._post("A Manually Titled Report")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertFalse(data["existing"])
        source = Source.objects.get(citation_key=data["key"])
        self.assertEqual(source.title, "A Manually Titled Report")

    @patch("engine.bibliography.metadata_resolvers.resolve_doi")
    def test_doi_resolves_metadata_and_creates(self, mock_resolve):
        mock_resolve.return_value = dict(_CSL)
        response = self._post("https://doi.org/10.1000/xyz123")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        mock_resolve.assert_called_once_with("10.1000/xyz123")
        source = Source.objects.get(citation_key=data["key"])
        self.assertEqual(source.title, "Deep Climate Signals")
        self.assertEqual(source.doi, "10.1000/xyz123")
        self.assertEqual(data["author"], "Vaughan")
        self.assertEqual(data["year"], "2025")

    @patch("engine.bibliography.metadata_resolvers.resolve_doi")
    def test_duplicate_doi_returns_existing(self, mock_resolve):
        mock_resolve.return_value = dict(_CSL)
        first = self._post("10.1000/xyz123").json()
        second_response = self._post("10.1000/xyz123")
        self.assertEqual(second_response.status_code, 200)
        second = second_response.json()
        self.assertTrue(second["existing"])
        self.assertEqual(second["key"], first["key"])
        self.assertEqual(Source.objects.count(), 1)

    @patch("engine.bibliography.metadata_resolvers.resolve_doi")
    def test_resolver_failure_creates_nothing(self, mock_resolve):
        mock_resolve.return_value = None
        response = self._post("10.9999/unknown")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(Source.objects.count(), 0)


class SourceChangeFormButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="admin", password="x", email="a@example.com"
        )

    def setUp(self):
        self.source_admin = SourceAdmin(Source, AdminSite())

    def _request(self, data):
        request = RequestFactory().post("/", data)
        request.user = self.admin_user
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    @patch("engine.bibliography.metadata_resolvers.resolve_doi")
    def test_fetch_doi_fills_empty_fields(self, mock_resolve):
        mock_resolve.return_value = dict(_CSL)
        source = Source.objects.create(
            citation_key="btn2026", title="Stub", doi="10.1000/xyz123"
        )
        response = self.source_admin.response_change(
            self._request({"_fetch_doi": "1"}), source
        )
        self.assertEqual(response.status_code, 302)
        source.refresh_from_db()
        self.assertEqual(source.container_title, "Nature Climate")
        self.assertEqual(source.authors, [{"family": "Vaughan", "given": "Ada"}])

    def test_fetch_doi_without_doi_warns(self):
        source = Source.objects.create(citation_key="nodoi2026", title="No DOI")
        response = self.source_admin.response_change(
            self._request({"_fetch_doi": "1"}), source
        )
        self.assertEqual(response.status_code, 302)

    @patch("engine.bibliography.link_checker.check_wayback_machine")
    @patch("engine.bibliography.link_checker.check_url")
    def test_check_url_records_archived_status(self, mock_check, mock_wayback):
        mock_check.return_value = {
            "status": "broken",
            "http_code": 404,
            "final_url": None,
        }
        mock_wayback.return_value = "https://web.archive.org/web/2026/dead"
        source = Source.objects.create(
            citation_key="chk2026", title="Rotting", url="https://example.com/dead"
        )
        response = self.source_admin.response_change(
            self._request({"_check_url": "1"}), source
        )
        self.assertEqual(response.status_code, 302)
        source.refresh_from_db()
        self.assertEqual(source.url_status, "archived")
        self.assertEqual(source.url_archive, "https://web.archive.org/web/2026/dead")
        self.assertEqual(source.url_check_count, 1)
        self.assertIsNotNone(source.url_last_checked)


class CitedInAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="admin", password="x", email="a@example.com"
        )
        cls.source = Source.objects.create(citation_key="cited2026", title="Cited")
        cls.uncited = Source.objects.create(citation_key="uncited2026", title="Uncited")
        cls.post = Post.objects.create(
            title="Citing Post",
            slug="citing-post",
            author=cls.admin_user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="Cited [@cited2026].",
        )
        PostCitation.objects.create(post=cls.post, source=cls.source, position=0)

    def setUp(self):
        self.source_admin = SourceAdmin(Source, AdminSite())

    def test_queryset_annotates_cited_count(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        row = self.source_admin.get_queryset(request).get(pk=self.source.pk)
        self.assertEqual(row._cited_count, 1)

    def test_cited_in_posts_links_citing_post(self):
        html = str(self.source_admin.cited_in_posts(self.source))
        self.assertIn("Citing Post", html)
        self.assertIn(f"/post/{self.post.pk}/change/", html)

    def test_cited_in_posts_handles_uncited(self):
        html = str(self.source_admin.cited_in_posts(self.uncited))
        self.assertIn("Not cited", html)
