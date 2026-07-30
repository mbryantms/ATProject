"""
Tests for the in-editor asset upload endpoint (admin:engine_post_upload_asset).

The endpoint backs paste/drop upload in the markdown editor: a file becomes
a ready, globally-referenceable Asset in one request, optionally attached
to the owning post/page — no post save or page reload involved.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from engine.models import Asset, Page, PageAsset, Post, PostAsset

User = get_user_model()

UPLOAD_URL = "admin:engine_post_upload_asset"

# Minimal valid-enough PNG payload; only the extension is validated.
PNG_BYTES = b"\x89PNG\r\n\x1a\nfakedata"


def _png(name="sunset-beach.png"):
    return SimpleUploadedFile(name, PNG_BYTES, content_type="image/png")


class EditorUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="writer", password="pw", is_staff=True
        )
        cls.post = Post.objects.create(
            title="Draft In Progress",
            content_markdown="Working…",
            author=cls.staff,
            published_at=timezone.now(),
        )
        cls.page = Page.objects.create(title="About", slug="about-test")

    def setUp(self):
        self.client.force_login(self.staff)

    def test_upload_creates_ready_asset_with_markdown_reference(self):
        resp = self.client.post(reverse(UPLOAD_URL), {"file": _png()})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["key"].startswith("img-"))
        self.assertEqual(data["asset_type"], "image")
        self.assertEqual(data["markdown"], f"![](@asset:{data['key']})")
        self.assertFalse(data["attached"])

        asset = Asset.objects.get(key=data["key"])
        self.assertEqual(asset.status, Asset.Status.READY)
        self.assertEqual(asset.title, "sunset-beach")
        self.assertEqual(asset.uploaded_by, self.staff)

    def test_upload_attaches_to_existing_post(self):
        resp = self.client.post(
            reverse(UPLOAD_URL),
            {"file": _png("diagram.png"), "object_id": str(self.post.pk)},
        )
        data = resp.json()
        self.assertTrue(data["attached"])
        self.assertTrue(
            PostAsset.objects.filter(post=self.post, asset__key=data["key"]).exists()
        )

    def test_upload_attaches_to_page(self):
        resp = self.client.post(
            reverse(UPLOAD_URL),
            {
                "file": _png("hero.png"),
                "object_id": str(self.page.pk),
                "owner_type": "page",
            },
        )
        data = resp.json()
        self.assertTrue(data["attached"])
        self.assertTrue(
            PageAsset.objects.filter(page=self.page, asset__key=data["key"]).exists()
        )

    def test_bad_object_id_still_creates_asset_unattached(self):
        resp = self.client.post(
            reverse(UPLOAD_URL), {"file": _png(), "object_id": "999999"}
        )
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data["attached"])
        self.assertTrue(Asset.objects.filter(key=data["key"]).exists())

    def test_explicit_title_wins_over_filename(self):
        resp = self.client.post(
            reverse(UPLOAD_URL), {"file": _png(), "title": "Golden Hour"}
        )
        data = resp.json()
        self.assertEqual(data["title"], "Golden Hour")
        self.assertTrue(data["key"].startswith("img-golden-hour"))

    def test_non_image_gets_link_markdown(self):
        pdf = SimpleUploadedFile(
            "paper.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        data = self.client.post(reverse(UPLOAD_URL), {"file": pdf}).json()
        self.assertEqual(data["asset_type"], "document")
        self.assertEqual(data["markdown"], f"[paper](@asset:{data['key']})")

    def test_disallowed_extension_rejected(self):
        exe = SimpleUploadedFile("evil.exe", b"MZ", content_type="application/what")
        resp = self.client.post(reverse(UPLOAD_URL), {"file": exe})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not allowed", resp.json()["error"])
        self.assertEqual(Asset.objects.count(), 0)

    @override_settings(ASSET_MAX_SIZES={"image": 4})
    def test_oversized_file_rejected(self):
        resp = self.client.post(reverse(UPLOAD_URL), {"file": _png()})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Asset.objects.count(), 0)

    def test_missing_file_rejected(self):
        resp = self.client.post(reverse(UPLOAD_URL), {})
        self.assertEqual(resp.status_code, 400)

    def test_get_not_allowed(self):
        resp = self.client.get(reverse(UPLOAD_URL))
        self.assertEqual(resp.status_code, 405)

    def test_anonymous_redirected_to_admin_login(self):
        self.client.logout()
        resp = self.client.post(reverse(UPLOAD_URL), {"file": _png()})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Asset.objects.count(), 0)

    def test_uploaded_asset_appears_in_autocomplete_immediately(self):
        """The completion endpoint is live, so a fresh upload is instantly
        suggestible without saving or reloading anything."""
        data = self.client.post(
            reverse(UPLOAD_URL), {"file": _png("unique-flower.png")}
        ).json()
        resp = self.client.get(
            reverse("admin:engine_post_autocomplete_assets"), {"q": "unique-flower"}
        )
        keys = [r["key"] for r in resp.json()["results"]]
        self.assertIn(data["key"], keys)
