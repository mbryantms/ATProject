"""
Tests for the syndication feeds (global, tag, category, series, featured),
in both RSS 2.0 and Atom 1.0 flavors.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.models import Category, Post, Series, Tag, TagAlias

User = get_user_model()


class FeedSetupMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="author",
            password="testpass123",
        )
        cls.tag = Tag.objects.create(name="Django", slug="django")
        cls.category = Category.objects.create(name="Tech", slug="tech")
        cls.series = Series.objects.create(title="My Series", slug="my-series")

        cls.published_post = Post.objects.create(
            title="Published Post",
            slug="published-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="# Hello\n\nFull body content.",
            content_html_cached="<h1>Hello</h1><p>Full body content.</p>",
            description="Short summary.",
        )
        cls.published_post.tags.add(cls.tag)
        cls.published_post.categories.add(cls.category)

        cls.featured_post = Post.objects.create(
            title="Featured Post",
            slug="featured-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            is_featured=True,
            content_html_cached="<p>Featured body.</p>",
        )

        cls.series_post = Post.objects.create(
            title="Series Post",
            slug="series-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            series=cls.series,
            series_order=1,
            content_html_cached="<p>Series body.</p>",
        )

        cls.draft_post = Post.objects.create(
            title="Draft Post",
            slug="draft-post",
            author=cls.user,
            status=Post.Status.DRAFT,
        )
        cls.private_post = Post.objects.create(
            title="Private Post",
            slug="private-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PRIVATE,
            published_at=timezone.now(),
        )


class GlobalFeedTests(FeedSetupMixin, TestCase):
    def test_rss_returns_200(self):
        response = self.client.get("/feed/")
        self.assertEqual(response.status_code, 200)
        # Feeds are deliberately served as application/xml (not
        # application/rss+xml) so browsers apply the XSLT stylesheet even
        # with X-Content-Type-Options: nosniff. See engine/feeds.py.
        self.assertIn("application/xml", response["Content-Type"])

    def test_atom_returns_200(self):
        response = self.client.get("/feed/atom/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])

    def test_rss_contains_published_public_post(self):
        response = self.client.get("/feed/")
        self.assertContains(response, "Published Post")

    def test_rss_excludes_drafts_and_private(self):
        response = self.client.get("/feed/")
        self.assertNotContains(response, "Draft Post")
        self.assertNotContains(response, "Private Post")

    def test_rss_includes_full_html_content(self):
        response = self.client.get("/feed/")
        # content_html_cached is escaped into the <description> element
        self.assertContains(response, "Full body content.")

    def test_rss_uses_stable_pk_guid(self):
        response = self.client.get("/feed/")
        body = response.content.decode("utf-8")
        self.assertIn(f"post:{self.published_post.pk}", body)
        self.assertIn('isPermaLink="false"', body)

    def test_rss_includes_both_tag_and_category_names(self):
        response = self.client.get("/feed/")
        body = response.content.decode("utf-8")
        self.assertIn("<category>Django</category>", body)
        self.assertIn("<category>Tech</category>", body)

    def test_rss_strips_browser_only_chrome(self):
        """Heading copy buttons, math copy bars, and duplicate reference-anchor
        numbers must not reach feed readers — they have no CSS to hide them."""
        self.published_post.content_html_cached = (
            "<h2>Example</h2>"
            '<button class="copy-section-link-button">x</button>'
            "<p>Body.</p>"
            '<span class="block-button-bar"><button class="copy">x</button></span>'
            '<ol><li class="reference-entry">'
            '<a href="#ref-foo" class="reference-anchor reference-ordinal">1.</a>'
            '<span class="reference-text">Author (2024).</span>'
            "</li></ol>"
        )
        self.published_post.save()
        response = self.client.get("/feed/")
        body = response.content.decode("utf-8")
        self.assertNotIn("copy-section-link-button", body)
        self.assertNotIn("block-button-bar", body)
        self.assertNotIn("reference-anchor", body)
        # Real content survives.
        self.assertIn("Author (2024).", body)
        self.assertIn("reference-entry", body)


class TagFeedTests(FeedSetupMixin, TestCase):
    def test_returns_200_for_known_slug(self):
        response = self.client.get(f"/feed/tag/{self.tag.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published Post")

    def test_returns_404_for_unknown_slug(self):
        response = self.client.get("/feed/tag/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_alias_resolves_to_canonical_tag(self):
        TagAlias.objects.create(alias="Django FW", slug="django-fw", tag=self.tag)
        response = self.client.get("/feed/tag/django-fw/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published Post")

    def test_atom_variant_returns_200(self):
        response = self.client.get(f"/feed/tag/{self.tag.slug}/atom/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])

    def test_excludes_posts_without_the_tag(self):
        response = self.client.get(f"/feed/tag/{self.tag.slug}/")
        self.assertNotContains(response, "Featured Post")
        self.assertNotContains(response, "Series Post")


class CategoryFeedTests(FeedSetupMixin, TestCase):
    def test_returns_200_for_known_slug(self):
        response = self.client.get(f"/feed/category/{self.category.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published Post")

    def test_returns_404_for_unknown_slug(self):
        response = self.client.get("/feed/category/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_excludes_posts_outside_category(self):
        response = self.client.get(f"/feed/category/{self.category.slug}/")
        self.assertNotContains(response, "Featured Post")


class SeriesFeedTests(FeedSetupMixin, TestCase):
    def test_returns_200_for_known_slug(self):
        response = self.client.get(f"/feed/series/{self.series.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Series Post")

    def test_returns_404_for_unknown_slug(self):
        response = self.client.get("/feed/series/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_excludes_posts_outside_series(self):
        response = self.client.get(f"/feed/series/{self.series.slug}/")
        self.assertNotContains(response, "Published Post")


class FeaturedFeedTests(FeedSetupMixin, TestCase):
    def test_returns_200(self):
        response = self.client.get("/feed/featured/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Featured Post")

    def test_excludes_unfeatured_posts(self):
        response = self.client.get("/feed/featured/")
        self.assertNotContains(response, "Published Post")
        self.assertNotContains(response, "Series Post")


class FeedTypeRegressionTests(FeedSetupMixin, TestCase):
    """
    Every RSS route must render without `'NoneType' object is not callable`,
    which is what happens if BasePostFeed.feed_type is set to None and
    shadows Django's Rss201rev2Feed default.
    """

    def test_every_rss_route_renders(self):
        urls = [
            "/feed/",
            "/feed/featured/",
            f"/feed/tag/{self.tag.slug}/",
            f"/feed/category/{self.category.slug}/",
            f"/feed/series/{self.series.slug}/",
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("application/xml", response["Content-Type"])

    def test_every_atom_route_renders(self):
        urls = [
            "/feed/atom/",
            "/feed/featured/atom/",
            f"/feed/tag/{self.tag.slug}/atom/",
            f"/feed/category/{self.category.slug}/atom/",
            f"/feed/series/{self.series.slug}/atom/",
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("application/xml", response["Content-Type"])


class FeedStylesheetTests(FeedSetupMixin, TestCase):
    """Every RSS and Atom feed must carry the XSLT processing instruction so
    browsers render a human-readable page instead of downloading XML.

    The URLs inside the PI must go through ``django.templatetags.static.static``
    so that manifest-hashed filenames are honored in production. We assert the
    URL contains the leaf name (rss.xsl / atom.xsl) but don't pin the exact
    path because staticfiles storage may add a hash in some configurations.
    """

    def test_rss_feed_links_rss_stylesheet(self):
        response = self.client.get("/feed/")
        body = response.content.decode("utf-8")
        self.assertIn("<?xml-stylesheet", body)
        self.assertRegex(body, r"/static/feeds/rss(\.[0-9a-f]+)?\.xsl")

    def test_atom_feed_links_atom_stylesheet(self):
        response = self.client.get("/feed/atom/")
        body = response.content.decode("utf-8")
        self.assertIn("<?xml-stylesheet", body)
        self.assertRegex(body, r"/static/feeds/atom(\.[0-9a-f]+)?\.xsl")

    def test_stylesheet_is_before_root_element(self):
        """PI must come after <?xml ...?> and before the root element."""
        response = self.client.get("/feed/")
        body = response.content.decode("utf-8")
        xml_decl_end = body.index("?>") + 2
        root_start = body.index("<rss")
        pi_start = body.index("<?xml-stylesheet")
        self.assertLess(xml_decl_end, pi_start)
        self.assertLess(pi_start, root_start)

    def test_scoped_feeds_carry_stylesheet(self):
        rss_pat = r"/static/feeds/rss(\.[0-9a-f]+)?\.xsl"
        atom_pat = r"/static/feeds/atom(\.[0-9a-f]+)?\.xsl"
        for url, pattern in [
            (f"/feed/tag/{self.tag.slug}/", rss_pat),
            (f"/feed/tag/{self.tag.slug}/atom/", atom_pat),
            (f"/feed/category/{self.category.slug}/", rss_pat),
            (f"/feed/series/{self.series.slug}/atom/", atom_pat),
            ("/feed/featured/", rss_pat),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRegex(response.content.decode("utf-8"), pattern)


class FeedIndexViewTests(FeedSetupMixin, TestCase):
    def test_feed_index_returns_200(self):
        response = self.client.get("/feeds/")
        self.assertEqual(response.status_code, 200)

    def test_feed_index_lists_global_and_featured(self):
        response = self.client.get("/feeds/")
        self.assertContains(response, "/feed/")
        self.assertContains(response, "/feed/atom/")
        self.assertContains(response, "/feed/featured/")
        self.assertContains(response, "/feed/featured/atom/")

    def test_feed_index_lists_categories_with_posts(self):
        response = self.client.get("/feeds/")
        self.assertContains(response, self.category.name)
        self.assertContains(response, f"/feed/category/{self.category.slug}/")

    def test_feed_index_lists_series_with_posts(self):
        response = self.client.get("/feeds/")
        self.assertContains(response, self.series.title)
        self.assertContains(response, f"/feed/series/{self.series.slug}/")

    def test_footer_links_feed_index(self):
        """The site footer should point readers at /feeds/ rather than /feed/."""
        response = self.client.get("/feeds/")
        body = response.content.decode("utf-8")
        # The footer is shared via base.html; /feeds/ link appears both in the
        # page content and the footer — ensure the footer anchor is present.
        self.assertIn('href="/feeds/"', body)
