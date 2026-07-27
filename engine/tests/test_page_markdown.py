"""Rich Markdown authoring and rendering parity for editable pages."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from engine.markdown.postprocessors.further_reading import further_reading_renderer
from engine.models import Asset, Page, PageAsset, PageFurtherReading, Source

User = get_user_model()


class PageRenderingTests(TestCase):
    def test_page_save_uses_page_context_and_extracts_toc(self):
        rendered = (
            '<section id="intro" class="level1">'
            '<h1 class="heading" id="intro">Intro</h1><p>Body</p></section>'
        )
        with mock.patch(
            "engine.models.page.render_markdown", return_value=rendered
        ) as render:
            page = Page.objects.create(
                slug="context-test",
                content="# Intro\n\nBody",
                first_line_caps=True,
            )

        context = render.call_args.kwargs["context"]
        self.assertIs(context["content_object"], page)
        self.assertTrue(context["first_line_caps"])
        self.assertEqual(page.table_of_contents[0]["id"], "intro")

    def test_page_further_reading_uses_content_object_context(self):
        page = Page.objects.create(slug="reading")
        source = Source.objects.create(
            citation_key="smith2026",
            title="Recommended work",
            source_type="book",
        )
        PageFurtherReading.objects.create(
            page=page,
            source=source,
            note="A useful follow-up.",
        )

        html = further_reading_renderer("<p>Body</p>", {"content_object": page})
        self.assertIn("Further Reading", html)
        self.assertIn("Recommended work", html)
        self.assertIn("A useful follow-up", html)

    def test_page_toc_renders_on_public_page(self):
        page = Page.objects.create(slug="about", title="About", show_toc=True)
        Page.objects.filter(pk=page.pk).update(
            content_html='<section><h2 id="history">History</h2></section>',
            table_of_contents=[
                {
                    "level": 2,
                    "id": "history",
                    "title": "History",
                    "title_html": "History",
                    "children": [],
                }
            ],
        )

        response = self.client.get(reverse("about"))
        self.assertContains(response, 'id="TOC"')
        self.assertContains(response, 'href="#history"')


class PageAssetTests(TestCase):
    def test_page_asset_updates_usage_count_and_supports_alias(self):
        page = Page.objects.create(slug="assets")
        asset = Asset.objects.create(
            title="Diagram",
            key="img-diagram",
            asset_type="image",
            status="ready",
        )
        page_asset = PageAsset.objects.create(
            page=page,
            asset=asset,
            alias="hero",
            custom_alt_text="Page-specific alt text",
        )

        asset.refresh_from_db()
        self.assertEqual(asset.usage_count, 1)
        self.assertEqual(page_asset.markdown_reference, "@hero")
        self.assertEqual(page_asset.get_alt_text(), "Page-specific alt text")


class PageAdminMarkdownTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="page-admin", password="pw", email="admin@example.com"
        )
        cls.page = Page.objects.create(slug="admin-page", title="Admin Page")
        cls.asset = Asset.objects.create(
            title="Admin diagram",
            key="img-admin-diagram",
            asset_type="image",
            status="ready",
        )
        PageAsset.objects.create(
            page=cls.page,
            asset=cls.asset,
            alias="diagram",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_change_form_has_shared_markdown_authoring_helpers(self):
        response = self.client.get(
            reverse("admin:engine_page_change", args=[self.page.pk])
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('data-cm-markdown-editor="1"', body)
        self.assertIn('data-cm-owner-type="page"', body)
        self.assertIn("data-md-helper-open", body)
        self.assertIn("Preview rendered markdown", body)
        self.assertIn("Browse &amp; insert citation", body)
        self.assertIn("Page Assets", body)
        self.assertIn("Further Reading (curated)", body)

    def test_asset_autocomplete_returns_page_local_alias(self):
        response = self.client.get(
            reverse("admin:engine_post_autocomplete_assets"),
            {
                "q": "diag",
                "owner_type": "page",
                "object_id": self.page.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(
            any(row["key"] == "diagram" and not row["global"] for row in results)
        )

    def test_linter_resolves_page_local_alias(self):
        response = self.client.post(
            reverse("admin:engine_post_lint_content"),
            {
                "content": "![Diagram](@diagram)",
                "owner_type": "page",
                "object_id": self.page.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        asset_messages = [
            item["message"]
            for item in response.json()["diagnostics"]
            if "asset" in item["message"].lower()
        ]
        self.assertEqual(asset_messages, [])

    def test_preview_supplies_page_rendering_context(self):
        with mock.patch(
            "engine.markdown.renderer.render_markdown", return_value="<p>Preview</p>"
        ) as render:
            response = self.client.post(
                reverse("admin:engine_post_preview_markdown"),
                {
                    "content": "Preview",
                    "owner_type": "page",
                    "object_id": self.page.pk,
                },
            )

        self.assertEqual(response.status_code, 200)
        context = render.call_args.kwargs["context"]
        self.assertEqual(context["content_object"], self.page)
        self.assertNotIn("post", context)
        self.assertContains(response, "Preview")
