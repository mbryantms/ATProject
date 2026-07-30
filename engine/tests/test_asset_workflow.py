"""
Tests for the editor asset-workflow endpoints: asset-info (hover cards /
drawer), and — as later phases land — the drawer listing, asset updates,
and rendition-driven cache re-renders.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from engine.models import Asset, AssetRendition, Post, PostAsset

User = get_user_model()

INFO_URL = "admin:engine_post_asset_info"


class AssetInfoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="writer", password="pw", is_staff=True
        )
        cls.asset = Asset.objects.create(
            title="Harbor",
            asset_type="image",
            key="img-harbor",
            status="ready",
            alt_text="Harbor at dusk",
            width=1600,
            height=900,
        )
        cls.post = Post.objects.create(
            title="Draft", content_markdown="x", author=cls.staff
        )
        cls.pa = PostAsset.objects.create(
            post=cls.post,
            asset=cls.asset,
            alias="hero",
            custom_alt_text="Override alt",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_global_ref_resolves(self):
        resp = self.client.get(reverse(INFO_URL), {"ref": "asset:img-harbor"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["key"], "img-harbor")
        self.assertEqual(data["asset_type"], "image")
        self.assertEqual(data["width"], 1600)
        self.assertFalse(data["attached"])
        self.assertEqual(data["alt_text"], "Harbor at dusk")
        self.assertEqual(data["renditions"], {"completed": 0, "total": 0})

    def test_alias_resolves_with_owner_and_overrides(self):
        resp = self.client.get(
            reverse(INFO_URL),
            {"ref": "hero", "object_id": str(self.post.pk), "owner_type": "post"},
        )
        data = resp.json()
        self.assertEqual(data["key"], "img-harbor")
        self.assertEqual(data["alias"], "hero")
        self.assertTrue(data["attached"])
        # The per-post override wins in the effective alt.
        self.assertEqual(data["alt_text"], "Override alt")

    def test_global_ref_reports_attachment_for_owner(self):
        resp = self.client.get(
            reverse(INFO_URL),
            {"ref": "asset:img-harbor", "object_id": str(self.post.pk)},
        )
        self.assertTrue(resp.json()["attached"])

    def test_rendition_counts_and_thumb(self):
        AssetRendition.objects.create(
            asset=self.asset,
            width=400,
            height=225,
            format="webp",
            quality=AssetRendition.Quality.HIGH,
            preset="",
            status=AssetRendition.Status.COMPLETED,
            file=SimpleUploadedFile("h-400.webp", b"fake", content_type="image/webp"),
            file_size=4,
        )
        AssetRendition.objects.create(
            asset=self.asset,
            width=800,
            height=450,
            format="webp",
            quality=AssetRendition.Quality.HIGH,
            preset="",
            status=AssetRendition.Status.PROCESSING,
            file=SimpleUploadedFile("h-800.webp", b"fake", content_type="image/webp"),
            file_size=4,
        )
        data = self.client.get(reverse(INFO_URL), {"ref": "asset:img-harbor"}).json()
        self.assertEqual(data["renditions"], {"completed": 1, "total": 2})
        self.assertIn("h-400", data["thumb"])

    def test_unknown_ref_404(self):
        resp = self.client.get(reverse(INFO_URL), {"ref": "asset:nope"})
        self.assertEqual(resp.status_code, 404)

    def test_missing_ref_400(self):
        self.assertEqual(self.client.get(reverse(INFO_URL)).status_code, 400)

    def test_anonymous_redirected(self):
        self.client.logout()
        resp = self.client.get(reverse(INFO_URL), {"ref": "asset:img-harbor"})
        self.assertEqual(resp.status_code, 302)

    def test_autocomplete_results_include_thumb_field(self):
        resp = self.client.get(
            reverse("admin:engine_post_autocomplete_assets"), {"q": "harbor"}
        )
        results = resp.json()["results"]
        self.assertTrue(results)
        self.assertIn("thumb", results[0])
