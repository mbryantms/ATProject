"""
Link-only ("unlisted") visibility contract.

An unlisted post is reachable by anyone who has its URL, but must never be
advertised anywhere on the site: the posts archive, tag pages and counts,
feeds, the sitemap, backlinks, or another post's similar-posts module. Its
own page carries a robots noindex meta so crawlers that follow a shared
link don't index it.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.models import InternalLink, Post, PostSimilarity, Tag

User = get_user_model()


def _make_post(author, slug, **overrides):
    defaults = dict(
        title=slug.replace("-", " ").title(),
        slug=slug,
        author=author,
        status=Post.Status.PUBLISHED,
        visibility=Post.Visibility.PUBLIC,
        published_at=timezone.now(),
        content_markdown=f"Body of {slug}.",
    )
    defaults.update(overrides)
    return Post.objects.create(**defaults)


class UnlistedVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = User.objects.create_user(username="author", password="x")
        cls.anchor = _make_post(author, "public-anchor")
        cls.control = _make_post(author, "public-control")
        cls.unlisted = _make_post(
            author, "unlisted-beacon", visibility=Post.Visibility.UNLISTED
        )
        cls.tag = Tag.objects.create(name="Shared")
        cls.anchor.tags.add(cls.tag)
        cls.unlisted.tags.add(cls.tag)
        # An unlisted post linking to a public one must not surface as a backlink.
        InternalLink.objects.create(source_post=cls.unlisted, target_post=cls.anchor)
        # Forced-score similarity rows, created after every signal-triggering
        # save above so the eager recompute task can't overwrite them.
        for target, score in ((cls.unlisted, 0.9), (cls.control, 0.8)):
            PostSimilarity.objects.update_or_create(
                source_post=cls.anchor, target_post=target, defaults={"score": score}
            )

    def test_reachable_by_direct_link_with_noindex(self):
        resp = self.client.get(self.unlisted.get_absolute_url())
        self.assertContains(resp, "Unlisted Beacon")
        self.assertContains(resp, '<meta name="robots" content="noindex">')

    def test_public_post_is_indexable(self):
        resp = self.client.get(self.anchor.get_absolute_url())
        self.assertNotContains(resp, 'content="noindex"')

    def test_absent_from_post_archive(self):
        resp = self.client.get("/posts/")
        self.assertContains(resp, "Public Anchor")
        self.assertNotContains(resp, "Unlisted Beacon")

    def test_absent_from_tag_archive_and_counts(self):
        resp = self.client.get(f"/tags/{self.tag.slug}/")
        self.assertContains(resp, "Public Anchor")
        self.assertNotContains(resp, "Unlisted Beacon")
        resp = self.client.get("/tags/")
        self.assertContains(resp, "(1)")  # only the public post is counted
        self.assertNotContains(resp, "(2)")

    def test_absent_from_global_feed(self):
        resp = self.client.get("/feed/")
        self.assertContains(resp, "Public Anchor")
        self.assertNotContains(resp, "Unlisted Beacon")

    def test_absent_from_sitemap(self):
        resp = self.client.get("/sitemap.xml")
        self.assertContains(resp, "public-anchor")
        self.assertNotContains(resp, "unlisted-beacon")

    def test_not_advertised_on_public_post_page(self):
        """Neither the similar-posts module nor backlinks may expose it."""
        resp = self.client.get(self.anchor.get_absolute_url())
        self.assertContains(resp, "Public Control")  # similar module rendered
        self.assertNotContains(resp, "Unlisted Beacon")

    def test_model_similar_posts_visibility(self):
        self.assertEqual(self.anchor.get_similar_posts(), [self.control])
        self.assertIn(
            self.unlisted, self.anchor.get_similar_posts(include_private=True)
        )
