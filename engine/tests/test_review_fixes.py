"""
Regression tests for the security, correctness, and reliability fixes applied
during the platform review.

Each test class documents the defect it guards against.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.bibliography.formatter import _format_fallback_entry
from engine.bibliography.net import UnsafeURLError, validate_public_url
from engine.bibliography.renderer import (
    render_bibliography_section,
    sanitize_citation_html,
)
from engine.models import (
    Category,
    InternalLink,
    Post,
    PostSlugHistory,
    Series,
    SiteSettings,
    Tag,
)

User = get_user_model()


class CitationXSSFallbackTests(TestCase):
    """
    Defect: the citeproc fallback formatter interpolated untrusted CSL fields
    (title, container, author) straight into HTML. Because citation rendering
    runs AFTER the markdown pipeline's nh3 sanitizer, a source title such as
    ``<img src=x onerror=...>`` reached the cached, ``|safe``-rendered page as a
    live element whenever the citeproc-js subprocess was unavailable.
    """

    MALICIOUS = {
        "title": "Pwn <img src=x onerror=alert(1)>",
        "container-title": "Evil <script>alert(2)</script> Journal",
        "author": [{"literal": "<b onclick=x>A</b>"}],
        "volume": "<svg onload=alert(3)>",
        "issued": {"date-parts": [[2024]]},
    }

    def test_fallback_entry_escapes_untrusted_fields(self):
        out = _format_fallback_entry(self.MALICIOUS)
        # No active injected markup survives (the payload tags are escaped, so
        # "onerror" persists only as inert text inside &lt;img ...&gt;).
        self.assertNotIn("<img", out)
        self.assertNotIn("<script", out)
        self.assertNotIn("<svg", out)
        self.assertNotIn("<b onclick", out)
        # Content is preserved, just escaped.
        self.assertIn("&lt;img", out)
        self.assertIn("&lt;script&gt;", out)
        # Structural markup this function emits is still present and active.
        self.assertIn('<div class="csl-entry">', out)
        self.assertIn("<i>", out)

    def test_bibliography_section_sanitizes_entry_html(self):
        # Even if a formatter emitted active markup, the renderer neutralizes it.
        hostile_entry = '<div class="csl-entry"><img src=x onerror=alert(1)>Bad</div>'
        html = render_bibliography_section([("k1", hostile_entry)])
        self.assertNotIn("onerror", html)
        self.assertNotIn("<img", html)
        # The reference list still renders.
        self.assertIn("reference-entry", html)

    def test_sanitize_citation_html_keeps_presentational_tags(self):
        frag = '<span class="csl-entry"><i>Title</i>, <b>2024</b></span>'
        out = sanitize_citation_html(frag)
        self.assertIn("<i>Title</i>", out)
        self.assertIn("<b>2024</b>", out)

    def test_sanitize_citation_html_strips_scripts_and_handlers(self):
        frag = (
            '<div>ok<script>alert(1)</script><a href="javascript:alert(2)">x</a></div>'
        )
        out = sanitize_citation_html(frag)
        self.assertNotIn("<script", out)
        self.assertNotIn("javascript:", out)


class SSRFGuardTests(TestCase):
    """
    Defect: DOI/URL resolvers and the link checker fetched Source-supplied URLs
    with urllib, which honors file:// (local file disclosure) and connects to
    internal/link-local addresses (SSRF to cloud metadata).
    """

    def test_file_scheme_blocked(self):
        with self.assertRaises(UnsafeURLError):
            validate_public_url("file:///etc/passwd")

    def test_non_http_schemes_blocked(self):
        for url in ("ftp://host/x", "gopher://host/x", "data:text/html,x"):
            with self.assertRaises(UnsafeURLError):
                validate_public_url(url)

    def test_cloud_metadata_ip_blocked(self):
        with self.assertRaises(UnsafeURLError):
            validate_public_url("http://169.254.169.254/latest/meta-data/")

    def test_loopback_blocked(self):
        with self.assertRaises(UnsafeURLError):
            validate_public_url("http://127.0.0.1/admin")

    def test_public_url_allowed(self):
        # Should not raise for a normal public host.
        validate_public_url("https://example.com/page")


class ExpireAtEnforcementTests(TestCase):
    """
    Defect: the documented ``expire_at`` unpublish time was validated in
    ``clean()`` but never enforced in any queryset, so expired posts stayed
    publicly visible everywhere.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="a", password="p", is_staff=True)
        now = timezone.now()
        cls.live = Post.objects.create(
            title="Live",
            slug="live",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=now - timedelta(days=2),
            content_markdown="live",
        )
        cls.expired = Post.objects.create(
            title="Expired",
            slug="expired",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=now - timedelta(days=2),
            expire_at=now - timedelta(days=1),
            content_markdown="expired",
        )
        cls.future_expiry = Post.objects.create(
            title="Future Expiry",
            slug="future-expiry",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=now - timedelta(days=2),
            expire_at=now + timedelta(days=10),
            content_markdown="future",
        )

    def test_published_excludes_expired(self):
        qs = Post.objects.published()
        self.assertIn(self.live, qs)
        self.assertIn(self.future_expiry, qs)
        self.assertNotIn(self.expired, qs)

    def test_is_published_false_when_expired(self):
        self.assertTrue(self.live.is_published)
        self.assertTrue(self.future_expiry.is_published)
        self.assertFalse(self.expired.is_published)

    def test_expired_post_detail_404_for_anonymous(self):
        resp = self.client.get(self.expired.get_absolute_url())
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get(self.live.get_absolute_url())
        self.assertEqual(resp.status_code, 200)


class HtmlCacheClearedOnEditTests(TestCase):
    """
    Defect: on a content change ``Post.save()`` cleared the TOC but not
    ``content_html_cached``, so the detail template served stale body HTML until
    the async re-render ran (or forever, if the worker/broker was down).
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="e", password="p", is_staff=True)

    def test_cache_cleared_when_markdown_changes(self):
        post = Post.objects.create(
            title="Cache Test",
            slug="cache-test",
            author=self.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="original body",
        )
        # Simulate a populated cache (the async task normally fills this).
        Post.all_objects.filter(pk=post.pk).update(
            content_html_cached="<p>STALE cached HTML</p>"
        )
        post.refresh_from_db()
        post.content_markdown = "a completely different body"
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.content_html_cached, "")

    def test_cache_preserved_when_only_metadata_changes(self):
        post = Post.objects.create(
            title="Meta Test",
            slug="meta-test",
            author=self.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="stable body",
        )
        Post.all_objects.filter(pk=post.pk).update(content_html_cached="<p>cached</p>")
        post.refresh_from_db()
        post.title = "Meta Test Renamed"  # metadata only, no markdown change
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.content_html_cached, "<p>cached</p>")


class SitemapVisibilityTests(TestCase):
    """
    Defect: taxonomy sitemaps joined on ``posts__status/visibility`` without
    excluding soft-deleted or future-dated posts, so a deleted/scheduled post
    could keep its tag/category/series page in the sitemap.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="s", password="p", is_staff=True)
        cls.tag = Tag.objects.create(name="solo", slug="solo")
        cls.category = Category.objects.create(name="Solo Cat", slug="solo-cat")
        cls.series = Series.objects.create(title="Solo Series", slug="solo-series")
        cls.post = Post.objects.create(
            title="Only Post",
            slug="only-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now() - timedelta(days=1),
            content_markdown="body",
            series=cls.series,
        )
        cls.post.tags.add(cls.tag)
        cls.post.categories.add(cls.category)

    def _sitemap_locations(self):
        resp = self.client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_taxonomy_present_when_post_visible(self):
        body = self._sitemap_locations()
        self.assertIn("/tags/solo/", body)
        self.assertIn("/categories/solo-cat/", body)
        self.assertIn("/series/solo-series/", body)

    def test_taxonomy_dropped_when_only_post_soft_deleted(self):
        self.post.delete(soft=True)
        body = self._sitemap_locations()
        self.assertNotIn("/tags/solo/", body)
        self.assertNotIn("/categories/solo-cat/", body)
        self.assertNotIn("/series/solo-series/", body)


class SlugRedirectTests(TestCase):
    """
    Feature: renaming a published post's slug used to 404 every inbound link.
    PostSlugHistory now records the old slug and the detail view 301-redirects.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sr", password="p", is_staff=True)

    def _make_post(self, slug):
        return Post.objects.create(
            title=slug.replace("-", " ").title(),
            slug=slug,
            author=self.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="body",
        )

    def test_rename_records_history_and_redirects(self):
        post = self._make_post("old-name")
        post.slug = "new-name"
        post.save()
        self.assertTrue(PostSlugHistory.objects.filter(old_slug="old-name").exists())
        resp = self.client.get("/posts/old-name/")
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp["Location"], "/posts/new-name/")

    def test_unknown_slug_still_404s(self):
        resp = self.client.get("/posts/never-existed/")
        self.assertEqual(resp.status_code, 404)

    def test_history_does_not_redirect_to_hidden_post(self):
        # A draft's former slug must not leak the draft to anonymous visitors.
        post = self._make_post("was-public")
        post.slug = "now-hidden"
        post.status = Post.Status.DRAFT
        post.save()
        resp = self.client.get("/posts/was-public/")
        self.assertEqual(resp.status_code, 404)


class ScheduledPublishRebuildTests(TestCase):
    """
    Defect: publish_scheduled_posts used a bulk .update(), which fires no
    post_save signal, so auto-published posts had no backlinks or similarity.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sp", password="p", is_staff=True)
        settings = SiteSettings.load()
        settings.enable_scheduled_publishing = True
        settings.save()

    def test_due_posts_publish_and_get_backlinks(self):
        from engine.tasks import publish_scheduled_posts

        past = timezone.now() - timedelta(minutes=5)
        target = Post.objects.create(
            title="Target",
            slug="target-post",
            author=self.user,
            status=Post.Status.SCHEDULED,
            visibility=Post.Visibility.PUBLIC,
            published_at=past,
            content_markdown="I am the target.",
        )
        source = Post.objects.create(
            title="Source",
            slug="source-post",
            author=self.user,
            status=Post.Status.SCHEDULED,
            visibility=Post.Visibility.PUBLIC,
            published_at=past,
            content_markdown="See [the target](/posts/target-post/).",
        )

        # While scheduled, the post_save signal skips link extraction.
        self.assertFalse(
            InternalLink.objects.filter(source_post=source, target_post=target).exists()
        )

        result = publish_scheduled_posts()
        self.assertEqual(result["published"], 2)

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(source.status, Post.Status.PUBLISHED)
        self.assertEqual(target.status, Post.Status.PUBLISHED)
        # Link extraction ran after the flip.
        self.assertTrue(
            InternalLink.objects.filter(source_post=source, target_post=target).exists()
        )

    def test_no_due_posts_returns_zero(self):
        from engine.tasks import publish_scheduled_posts

        Post.objects.create(
            title="Future",
            slug="future-post",
            author=self.user,
            status=Post.Status.SCHEDULED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now() + timedelta(days=1),
            content_markdown="later",
        )
        result = publish_scheduled_posts()
        self.assertEqual(result["published"], 0)


class ArchivePaginationTests(TestCase):
    """Archive pagination bounds page size and preserves the sort param."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pg", password="p", is_staff=True)
        now = timezone.now()
        for i in range(5):
            Post.objects.create(
                title=f"Post {i}",
                slug=f"post-{i}",
                author=cls.user,
                status=Post.Status.PUBLISHED,
                visibility=Post.Visibility.PUBLIC,
                published_at=now - timedelta(days=i),
                content_markdown=f"body {i}",
            )

    def test_single_page_when_under_limit(self):
        # Default page size is generous; a handful of posts render on one page.
        resp = self.client.get("/posts/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'class="pagination"')

    def test_paginates_and_preserves_sort(self):
        import engine.views as views_module

        original = views_module.ARCHIVE_PAGE_SIZE
        views_module.ARCHIVE_PAGE_SIZE = 2
        try:
            resp = self.client.get("/posts/?sort=date")
            self.assertContains(resp, 'class="pagination"')
            self.assertContains(resp, "sort=date&amp;page=2")
            resp2 = self.client.get("/posts/?sort=date&page=2")
            self.assertEqual(resp2.status_code, 200)
        finally:
            views_module.ARCHIVE_PAGE_SIZE = original
