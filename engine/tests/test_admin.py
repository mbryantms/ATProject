"""
Tests for the Django admin: page loads, permissions, soft-delete visibility,
the read-only mixin, namespace-safe links, navigation ordering, and a
query-count regression guard for the facets fix.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from engine.admin.display import admin_change_link, admin_changelist_link, mk_pill
from engine.admin.post import PostAdmin, PostRevisionAdmin
from engine.models import Category, Post, PostRevision, Series, Tag

User = get_user_model()


class AdminSetupMixin:
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="admin", password="pw", email="a@example.com"
        )
        cls.tag = Tag.objects.create(name="Django", slug="django")
        cls.category = Category.objects.create(name="Essays", slug="essays")
        cls.series = Series.objects.create(title="A Series", slug="a-series")
        cls.post = Post.objects.create(
            title="Hello World",
            slug="hello-world",
            author=cls.superuser,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="# Hi",
        )
        cls.post.tags.add(cls.tag)
        cls.post.categories.add(cls.category)

    def setUp(self):
        self.client.force_login(self.superuser)


class AdminPagesLoadTests(AdminSetupMixin, TestCase):
    """Every registered engine changelist and the custom views load."""

    ENGINE_MODELS = [
        "post",
        "page",
        "series",
        "category",
        "tag",
        "tagalias",
        "source",
        "asset",
        "assetfolder",
        "assettag",
        "assetcollection",
        "assetmetadata",
        "assetrendition",
        "sitesettings",
        "internallink",
        "postrevision",
        "postsimilarity",
        "postslughistory",
    ]

    def test_changelists_load(self):
        for model in self.ENGINE_MODELS:
            resp = self.client.get(f"/manage/engine/{model}/")
            self.assertEqual(resp.status_code, 200, f"{model} changelist failed")

    def test_post_change_form_loads(self):
        url = reverse("admin:engine_post_change", args=[self.post.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_custom_views_load(self):
        for name in ["celery_status"]:
            self.assertEqual(self.client.get(reverse(f"admin:{name}")).status_code, 200)


class SoftDeleteAdminTests(AdminSetupMixin, TestCase):
    """The soft-delete mixin must actually run (base-class order was wrong)."""

    def test_post_admin_shows_soft_deleted(self):
        self.post.delete(soft=True)
        # Default manager hides it; the admin must still list it for restore.
        self.assertNotIn(self.post, Post.objects.all())
        ma = PostAdmin(Post, admin.site)
        req = RequestFactory().get("/")
        req.user = self.superuser
        self.assertIn(self.post, ma.get_queryset(req))

    def test_asset_admin_uses_all_objects(self):
        from engine.admin.asset import AssetAdmin

        # MRO must place the mixin before ModelAdmin so its get_queryset runs.
        mro = [c.__name__ for c in AssetAdmin.__mro__]
        self.assertLess(mro.index("SoftDeleteAdminMixin"), mro.index("ModelAdmin"))


class ReadOnlyAdminTests(AdminSetupMixin, TestCase):
    """Diagnostic admins disable add/change AND delete."""

    def test_read_only_admins_block_all_writes(self):
        from engine.admin.post import (
            InternalLinkAdmin,
            PostSimilarityAdmin,
            PostSlugHistoryAdmin,
        )

        req = RequestFactory().get("/")
        req.user = self.superuser
        for cls in [
            InternalLinkAdmin,
            PostRevisionAdmin,
            PostSimilarityAdmin,
            PostSlugHistoryAdmin,
        ]:
            ma = cls(PostRevision, admin.site)
            self.assertFalse(ma.has_add_permission(req))
            self.assertFalse(ma.has_change_permission(req))
            self.assertFalse(ma.has_delete_permission(req))


class DestructiveViewPermissionTests(AdminSetupMixin, TestCase):
    """Destructive custom views enforce object/model permissions."""

    def test_revision_restore_denied_without_change_perm(self):
        # Post.save() already created revision v1; add a distinct one.
        rev = PostRevision.objects.create(
            post=self.post, version=99, content_markdown="old body"
        )
        staff = User.objects.create_user(
            username="viewer", password="pw", is_staff=True
        )
        # Give only *view* permission on Post, not change.
        from django.contrib.auth.models import Permission

        staff.user_permissions.add(Permission.objects.get(codename="view_post"))
        self.client.force_login(staff)
        url = reverse("admin:engine_post_revision_restore", args=[self.post.pk, rev.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)
        self.post.refresh_from_db()
        self.assertNotEqual(self.post.content_markdown, "old body")

    def test_asset_cleanup_denied_without_delete_perm(self):
        staff = User.objects.create_user(
            username="viewer2", password="pw", is_staff=True
        )
        self.client.force_login(staff)
        resp = self.client.get("/manage/engine/asset/cleanup/")
        self.assertEqual(resp.status_code, 403)


class NamespaceSafeLinkTests(AdminSetupMixin, TestCase):
    """Admin links use reverse() so they work at the /manage/ mount, not /admin/."""

    def test_tag_changelist_links_resolve_to_manage(self):
        body = self.client.get("/manage/engine/tag/").content.decode()
        self.assertIn("/manage/engine/post/", body)
        self.assertNotIn("/admin/engine/", body)

    def test_admin_change_link_helper(self):
        html = str(admin_change_link(self.post, "x"))
        self.assertIn(reverse("admin:engine_post_change", args=[self.post.pk]), html)

    def test_admin_changelist_link_helper(self):
        html = str(admin_changelist_link(Post, "3", tags__id__exact=self.tag.pk))
        self.assertIn("/manage/engine/post/", html)
        self.assertIn(f"tags__id__exact={self.tag.pk}", html)


class DisplayHelperTests(TestCase):
    def test_mk_pill_valid_tone(self):
        self.assertIn("mk-pill--success", str(mk_pill("Done", "success")))

    def test_mk_pill_unknown_tone_falls_back(self):
        self.assertIn("mk-pill--muted", str(mk_pill("?", "bogus")))

    def test_mk_pill_escapes(self):
        self.assertNotIn("<script>", str(mk_pill("<script>", "info")))


class NavigationOrderingTests(AdminSetupMixin, TestCase):
    def test_content_before_diagnostics(self):
        req = RequestFactory().get("/manage/")
        req.user = self.superuser
        app_list = admin.site.get_app_list(req)
        engine = next(a for a in app_list if a["app_label"] == "engine")
        names = [m["object_name"] for m in engine["models"]]
        self.assertLess(names.index("Post"), names.index("InternalLink"))
        self.assertLess(names.index("Post"), names.index("PostSimilarity"))


class ChangelistQueryCountTests(AdminSetupMixin, TestCase):
    """Guard against the facets regression (was ~75 queries)."""

    def test_post_changelist_query_budget(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get("/manage/engine/post/")
        self.assertEqual(resp.status_code, 200)
        self.assertLess(
            len(ctx.captured_queries),
            25,
            f"Post changelist used {len(ctx.captured_queries)} queries "
            "(facets should be ALLOW, not ALWAYS)",
        )
