"""
Tests for core model behavior: soft delete, querysets, managers, and field logic.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.models import (
    Category,
    Post,
    Series,
    Source,
    Tag,
    TagAlias,
)

User = get_user_model()


class TestSetupMixin:
    """Shared setup for model tests."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="testauthor",
            password="testpass123",
            is_staff=True,
        )


class PostQuerySetTests(TestSetupMixin, TestCase):
    """Test Post custom queryset methods."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        now = timezone.now()
        cls.published_public = Post.objects.create(
            title="Public Post",
            slug="public-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=now,
            content_markdown="Hello world",
        )
        cls.published_unlisted = Post.objects.create(
            title="Unlisted Post",
            slug="unlisted-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.UNLISTED,
            published_at=now,
            content_markdown="Unlisted",
        )
        cls.draft = Post.objects.create(
            title="Draft Post",
            slug="draft-post",
            author=cls.user,
            status=Post.Status.DRAFT,
            content_markdown="Draft",
        )
        cls.private = Post.objects.create(
            title="Private Post",
            slug="private-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PRIVATE,
            published_at=now,
            content_markdown="Private",
        )

    def test_published_returns_only_published(self):
        qs = Post.objects.published()
        self.assertIn(self.published_public, qs)
        self.assertIn(self.published_unlisted, qs)
        self.assertIn(self.private, qs)
        self.assertNotIn(self.draft, qs)

    def test_public_returns_public_and_unlisted(self):
        qs = Post.objects.published().public()
        self.assertIn(self.published_public, qs)
        self.assertIn(self.published_unlisted, qs)
        self.assertNotIn(self.private, qs)

    def test_drafts_returns_only_drafts(self):
        qs = Post.objects.drafts()
        self.assertIn(self.draft, qs)
        self.assertNotIn(self.published_public, qs)


class SoftDeleteTests(TestSetupMixin, TestCase):
    """Test soft delete behavior across models."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.post = Post.objects.create(
            title="Deletable Post",
            slug="deletable-post",
            author=cls.user,
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at=timezone.now(),
            content_markdown="To be deleted",
        )

    def test_soft_delete_hides_from_default_manager(self):
        self.post.delete(soft=True)
        self.assertNotIn(self.post, Post.objects.all())

    def test_soft_delete_visible_via_all_objects(self):
        self.post.delete(soft=True)
        self.assertIn(self.post, Post.all_objects.all())

    def test_soft_delete_sets_is_deleted_flag(self):
        self.post.delete(soft=True)
        self.post.refresh_from_db()
        self.assertTrue(self.post.is_deleted)

    def test_soft_delete_sets_deleted_at(self):
        self.post.delete(soft=True)
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.deleted_at)


class PostModelTests(TestSetupMixin, TestCase):
    """Test Post model field logic."""

    def test_word_count_computed_on_save(self):
        post = Post.objects.create(
            title="Word Count Test",
            slug="word-count-test",
            author=self.user,
            content_markdown="one two three four five",
        )
        self.assertEqual(post.word_count, 5)

    def test_view_count_starts_at_zero(self):
        post = Post.objects.create(
            title="View Count Test",
            slug="view-count-test",
            author=self.user,
            content_markdown="Test",
        )
        self.assertEqual(post.view_count, 0)

    def test_slug_unique(self):
        Post.objects.create(
            title="First",
            slug="unique-slug",
            author=self.user,
            content_markdown="First",
        )
        with self.assertRaises(Exception):
            Post.objects.create(
                title="Second",
                slug="unique-slug",
                author=self.user,
                content_markdown="Second",
            )


class TagTests(TestCase):
    """Test Tag model behavior."""

    def test_tag_creation(self):
        tag = Tag.objects.create(name="Python", slug="python")
        self.assertEqual(str(tag), "Python")
        self.assertTrue(tag.is_active)

    def test_tag_alias_redirect(self):
        tag = Tag.objects.create(name="Machine Learning", slug="machine-learning")
        alias = TagAlias.objects.create(name="ML", slug="ml", tag=tag)
        self.assertEqual(alias.tag, tag)

    def test_hierarchical_tags(self):
        parent = Tag.objects.create(name="Programming", slug="programming")
        child = Tag.objects.create(name="Python", slug="python", parent=parent)
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children.all())

    def test_bulk_update_usage_counts(self):
        tag = Tag.objects.create(name="Test Tag", slug="test-tag", usage_count=99)
        # No posts linked, so usage_count should become 0
        Tag.bulk_update_usage_counts()
        tag.refresh_from_db()
        self.assertEqual(tag.usage_count, 0)


class CategoryTests(TestCase):
    """Test Category model."""

    def test_category_creation(self):
        cat = Category.objects.create(name="Tech", slug="tech")
        self.assertEqual(str(cat), "Tech")

    def test_hierarchical_categories(self):
        parent = Category.objects.create(name="Tech", slug="tech")
        child = Category.objects.create(name="Web Dev", slug="web-dev", parent=parent)
        self.assertEqual(child.parent, parent)


class SeriesTests(TestSetupMixin, TestCase):
    """Test Series model."""

    def test_series_creation(self):
        series = Series.objects.create(title="My Series", slug="my-series")
        self.assertEqual(str(series), "My Series")


class SourceTests(TestCase):
    """Test Source model and citation key generation."""

    def test_source_creation_with_auto_key(self):
        source = Source.objects.create(
            title="A Study on Testing",
            source_type="article-journal",
            authors=[{"family": "Smith", "given": "John"}],
            issued_date={"date-parts": [[2024]]},
        )
        self.assertTrue(source.citation_key)
        self.assertRegex(source.citation_key, r"^[a-z0-9][a-z0-9_-]*$")

    def test_citation_key_unique(self):
        Source.objects.create(
            citation_key="smith2024",
            title="First Study",
            source_type="article-journal",
        )
        # Second source with same author/year should get a different key
        source2 = Source.objects.create(
            title="Second Study",
            source_type="article-journal",
            authors=[{"family": "Smith", "given": "John"}],
            issued_date={"date-parts": [[2024]]},
        )
        self.assertNotEqual(source2.citation_key, "smith2024")
