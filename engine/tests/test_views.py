"""
Tests for public-facing views: homepage, archive, post detail, etc.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.models import Category, Post, Tag

User = get_user_model()


class TestSetupMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="author",
            password="testpass123",
            is_staff=True,
        )
        cls.tag = Tag.objects.create(name="Django", slug="django")
        cls.category = Category.objects.create(name="Tech", slug="tech")
        cls.published_post = Post.objects.create(
            title="Published Post",
            slug="published-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="# Hello\n\nThis is a test post.",
            content_html_cached="<h1>Hello</h1><p>This is a test post.</p>",
        )
        cls.published_post.tags.add(cls.tag)
        cls.published_post.categories.add(cls.category)
        cls.draft_post = Post.objects.create(
            title="Draft Post",
            slug="draft-post",
            author=cls.user,
            status=Post.Status.DRAFT,
            content_markdown="Draft content",
        )


class IndexViewTests(TestSetupMixin, TestCase):
    def test_homepage_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_homepage_contains_newest_posts(self):
        response = self.client.get("/")
        self.assertContains(response, "Published Post")

    def test_homepage_hides_drafts_from_anonymous(self):
        response = self.client.get("/")
        self.assertNotContains(response, "Draft Post")


class PostArchiveViewTests(TestSetupMixin, TestCase):
    def test_archive_returns_200(self):
        response = self.client.get("/posts/")
        self.assertEqual(response.status_code, 200)

    def test_archive_contains_published_posts(self):
        response = self.client.get("/posts/")
        self.assertContains(response, "Published Post")

    def test_archive_hides_drafts(self):
        response = self.client.get("/posts/")
        self.assertNotContains(response, "Draft Post")

    def test_archive_sort_by_title(self):
        response = self.client.get("/posts/?sort=title")
        self.assertEqual(response.status_code, 200)

    def test_archive_invalid_sort_defaults_to_date(self):
        response = self.client.get("/posts/?sort=invalid")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "date")


class PostDetailViewTests(TestSetupMixin, TestCase):
    def test_published_post_returns_200(self):
        response = self.client.get(f"/posts/{self.published_post.slug}/")
        self.assertEqual(response.status_code, 200)

    def test_draft_post_returns_404_for_anonymous(self):
        response = self.client.get(f"/posts/{self.draft_post.slug}/")
        self.assertEqual(response.status_code, 404)

    def test_draft_post_visible_to_staff(self):
        self.client.login(username="author", password="testpass123")
        response = self.client.get(f"/posts/{self.draft_post.slug}/")
        self.assertEqual(response.status_code, 200)

    def test_view_count_increments_for_anonymous(self):
        initial_count = self.published_post.view_count
        self.client.get(f"/posts/{self.published_post.slug}/")
        self.published_post.refresh_from_db()
        self.assertEqual(self.published_post.view_count, initial_count + 1)

    def test_view_count_does_not_increment_for_staff(self):
        self.client.login(username="author", password="testpass123")
        initial_count = self.published_post.view_count
        self.client.get(f"/posts/{self.published_post.slug}/")
        self.published_post.refresh_from_db()
        self.assertEqual(self.published_post.view_count, initial_count)

    def test_nonexistent_slug_returns_404(self):
        response = self.client.get("/posts/nonexistent-slug/")
        self.assertEqual(response.status_code, 404)


class TagViewTests(TestSetupMixin, TestCase):
    def test_tag_archive_returns_200(self):
        response = self.client.get(f"/tags/{self.tag.slug}/")
        self.assertEqual(response.status_code, 200)

    def test_tag_list_returns_200(self):
        response = self.client.get("/tags/")
        self.assertEqual(response.status_code, 200)

    def test_nonexistent_tag_returns_404(self):
        response = self.client.get("/tags/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_tag_alias_redirects(self):
        from engine.models import TagAlias

        TagAlias.objects.create(alias="Django FW", slug="django-fw", tag=self.tag)
        response = self.client.get("/tags/django-fw/")
        self.assertEqual(response.status_code, 301)


class CategoryViewTests(TestSetupMixin, TestCase):
    def test_category_archive_returns_200(self):
        response = self.client.get(f"/categories/{self.category.slug}/")
        self.assertEqual(response.status_code, 200)

    def test_category_list_returns_200(self):
        response = self.client.get("/categories/")
        self.assertEqual(response.status_code, 200)


class SearchViewTests(TestSetupMixin, TestCase):
    def test_search_page_returns_200(self):
        response = self.client.get("/search/")
        self.assertEqual(response.status_code, 200)

    def test_search_with_query(self):
        response = self.client.get("/search/?q=test")
        self.assertEqual(response.status_code, 200)


class SitemapTests(TestSetupMixin, TestCase):
    def test_sitemap_returns_200(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])

    def test_robots_txt_returns_200(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])
        self.assertContains(response, "Sitemap:")


class HealthCheckTests(TestCase):
    def test_health_check_returns_200(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)

    def test_404_page(self):
        response = self.client.get("/nonexistent-url/")
        self.assertEqual(response.status_code, 404)
