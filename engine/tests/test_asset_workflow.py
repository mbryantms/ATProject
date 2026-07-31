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


class AssetsPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="panelist", password="pw", is_staff=True
        )
        cls.post = Post.objects.create(
            title="Panel Draft", content_markdown="x", author=cls.staff
        )
        cls.attached_asset = Asset.objects.create(
            title="Attached One", asset_type="image", key="img-attached", status="ready"
        )
        PostAsset.objects.create(post=cls.post, asset=cls.attached_asset, alias="hero")
        cls.loose_asset = Asset.objects.create(
            title="Loose Two", asset_type="image", key="img-loose", status="ready"
        )
        cls.doc_asset = Asset.objects.create(
            title="A Document", asset_type="document", key="doc-notes", status="ready"
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _get(self, **params):
        return self.client.get(reverse("admin:engine_post_assets_panel"), params).json()

    def test_attached_and_library_returned(self):
        data = self._get(object_id=str(self.post.pk))
        self.assertEqual([a["key"] for a in data["attached"]], ["img-attached"])
        self.assertEqual(data["attached"][0]["alias"], "hero")
        library_keys = {a["key"] for a in data["library"]}
        self.assertEqual(library_keys, {"img-attached", "img-loose", "doc-notes"})
        by_key = {a["key"]: a for a in data["library"]}
        self.assertTrue(by_key["img-attached"]["attached"])
        self.assertFalse(by_key["img-loose"]["attached"])

    def test_search_filters_library(self):
        data = self._get(q="loose")
        self.assertEqual([a["key"] for a in data["library"]], ["img-loose"])

    def test_type_filter(self):
        data = self._get(type="document")
        self.assertEqual([a["key"] for a in data["library"]], ["doc-notes"])

    def test_library_total_reported(self):
        data = self._get()
        self.assertEqual(data["library_total"], 3)

    def test_anonymous_redirected(self):
        self.client.logout()
        resp = self.client.get(reverse("admin:engine_post_assets_panel"))
        self.assertEqual(resp.status_code, 302)


class UpdateAssetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="editor", password="pw", is_staff=True
        )
        cls.asset = Asset.objects.create(
            title="Editable", asset_type="image", key="img-editable", status="ready"
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _post(self, **fields):
        return self.client.post(reverse("admin:engine_post_update_asset"), fields)

    def test_updates_alt_and_caption(self):
        resp = self._post(key="img-editable", alt_text="New alt", caption="New caption")
        self.assertEqual(resp.status_code, 200)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.alt_text, "New alt")
        self.assertEqual(self.asset.caption, "New caption")
        self.assertEqual(resp.json()["alt_text"], "New alt")

    def test_empty_title_rejected(self):
        resp = self._post(key="img-editable", title="   ")
        self.assertEqual(resp.status_code, 400)

    def test_unknown_key_404(self):
        self.assertEqual(self._post(key="img-nope", alt_text="x").status_code, 404)

    def test_no_fields_400(self):
        self.assertEqual(self._post(key="img-editable").status_code, 400)

    def test_focal_point_validation(self):
        self.assertEqual(
            self._post(key="img-editable", focal_point_x="1.5").status_code, 400
        )
        resp = self._post(
            key="img-editable", focal_point_x="0.25", focal_point_y="0.75"
        )
        self.assertEqual(resp.status_code, 200)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.focal_point_x, 0.25)
        self.assertEqual(self.asset.focal_point_y, 0.75)

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("admin:engine_post_update_asset"))
        self.assertEqual(resp.status_code, 405)


class AttachAssetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="attacher", password="pw", is_staff=True
        )
        cls.post = Post.objects.create(
            title="Attach Draft", content_markdown="x", author=cls.staff
        )
        cls.asset = Asset.objects.create(
            title="Attachable", asset_type="image", key="img-attachable", status="ready"
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_attach_and_idempotent(self):
        url = reverse("admin:engine_post_attach_asset")
        for _ in range(2):
            resp = self.client.post(
                url,
                {
                    "key": "img-attachable",
                    "object_id": str(self.post.pk),
                    "owner_type": "post",
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["attached"])
        self.assertEqual(
            PostAsset.objects.filter(post=self.post, asset=self.asset).count(), 1
        )

    def test_unknown_owner_404(self):
        resp = self.client.post(
            reverse("admin:engine_post_attach_asset"),
            {"key": "img-attachable", "object_id": "999999"},
        )
        self.assertEqual(resp.status_code, 404)


class PreviewRenderCacheTests(TestCase):
    """The live split preview re-posts on typing pauses; identical content
    must hit the render cache instead of re-running the pandoc pipeline."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="previewer", password="pw", is_staff=True
        )
        cls.post = Post.objects.create(
            title="Cache Draft", content_markdown="x", author=cls.staff
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _preview(self, content, object_id=""):
        params = {"content": content}
        if object_id:
            params["object_id"] = object_id
        return self.client.post(reverse("admin:engine_post_preview_markdown"), params)

    def test_identical_content_renders_once(self):
        from unittest import mock

        from django.test import override_settings

        caches = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "preview-cache-test",
            }
        }
        with override_settings(CACHES=caches):
            with mock.patch(
                "engine.markdown.renderer.render_markdown",
                return_value="<p>rendered</p>",
            ) as rm:
                for _ in range(2):
                    resp = self._preview("Hello *world*")
                    self.assertTrue(resp.json()["ok"])
                self.assertEqual(rm.call_count, 1)

                # Different content: a fresh render.
                self._preview("Hello *world* changed")
                self.assertEqual(rm.call_count, 2)

                # Same content but owner-scoped: alias resolution can differ,
                # so it must not share the anonymous entry.
                self._preview("Hello *world*", object_id=str(self.post.pk))
                self.assertEqual(rm.call_count, 3)


class RenditionRerenderTests(TestCase):
    """Completing renditions must queue cached-HTML re-renders for every
    post that embeds the asset (attached or via a global reference)."""

    @classmethod
    def setUpTestData(cls):
        author = User.objects.create_user(username="rerender", password="x")
        cls.asset = Asset.objects.create(
            title="Baked", asset_type="image", key="img-baked", status="ready"
        )
        cls.attached_post = Post.objects.create(
            title="Attached Ref", content_markdown="![](@hero)", author=author
        )
        PostAsset.objects.create(post=cls.attached_post, asset=cls.asset, alias="hero")
        cls.global_post = Post.objects.create(
            title="Global Ref",
            content_markdown="![x](@asset:img-baked)",
            author=author,
        )
        cls.unrelated_post = Post.objects.create(
            title="Unrelated", content_markdown="No images here.", author=author
        )

    def test_referencing_posts_queued(self):
        from unittest import mock

        from engine.tasks import _rerender_posts_referencing_asset

        with mock.patch("engine.tasks.update_post_derived_content") as task:
            _rerender_posts_referencing_asset(self.asset)
        queued = {call.args[0] for call in task.delay.call_args_list}
        self.assertEqual(queued, {self.attached_post.pk, self.global_post.pk})


class FocalPointPayloadTests(TestCase):
    def test_info_payload_carries_focal_points(self):
        staff = User.objects.create_user(username="focal", password="pw", is_staff=True)
        Asset.objects.create(
            title="Focal",
            asset_type="image",
            key="img-focal",
            status="ready",
            focal_point_x=0.3,
            focal_point_y=0.7,
        )
        self.client.force_login(staff)
        data = self.client.get(reverse(INFO_URL), {"ref": "asset:img-focal"}).json()
        self.assertEqual(data["focal_point_x"], 0.3)
        self.assertEqual(data["focal_point_y"], 0.7)
