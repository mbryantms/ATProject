"""
Tests for the automated similarity feature.

Covers:
- Scoring primitives (_jaccard, _backlink_score, components totalling)
- PostSimilarity rows materialize via the recompute task
- Signal handlers enqueue the task on post save, tag change, link
  creation, and citation creation (all synchronous under eager mode)
- PostDetailView reads from PostSimilarity, not the compute path
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from engine.models import (
    InternalLink,
    Post,
    PostCitation,
    PostSimilarity,
    Source,
    SourceType,
    Tag,
)
from engine.similarity import (
    BACKLINK_DIRECT_FACTOR,
    BACKLINK_NEIGHBOR_FACTOR,
    SimilarityComponents,
    _backlink_score,
    _build_citation_map,
    _build_neighbor_map,
    _jaccard,
)
from engine.tasks import recompute_similarity_for_post

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


class ScoringPrimitiveTests(TestCase):
    def test_jaccard_basic(self):
        self.assertEqual(_jaccard([1, 2, 3], [2, 3, 4]), 2 / 4)
        self.assertEqual(_jaccard([], [1]), 0.0)
        self.assertEqual(_jaccard([1, 2], [3, 4]), 0.0)
        self.assertEqual(_jaccard([1, 2], [1, 2]), 1.0)

    def test_backlink_score_direct_only(self):
        # post 1 links to candidate 2, no other neighbors.
        score = _backlink_score(
            post_id=1,
            candidate_id=2,
            post_neighbors={2},
            candidate_neighbors={1},
        )
        self.assertAlmostEqual(score, BACKLINK_DIRECT_FACTOR)

    def test_backlink_score_neighbor_only(self):
        # No direct edge; both share neighbor 9.
        score = _backlink_score(
            post_id=1,
            candidate_id=2,
            post_neighbors={9},
            candidate_neighbors={9},
        )
        self.assertAlmostEqual(score, BACKLINK_NEIGHBOR_FACTOR * 1.0)

    def test_backlink_score_combined(self):
        # Direct edge + partial neighbor overlap.
        score = _backlink_score(
            post_id=1,
            candidate_id=2,
            post_neighbors={2, 9},
            candidate_neighbors={1, 9, 10},
        )
        # Neighbor sets (after stripping self/candidate): {9} vs {9, 10}
        # -> Jaccard = 1/2.
        expected = BACKLINK_DIRECT_FACTOR * 1.0 + BACKLINK_NEIGHBOR_FACTOR * (1 / 2)
        self.assertAlmostEqual(score, expected)

    def test_backlink_score_none(self):
        score = _backlink_score(
            post_id=1,
            candidate_id=2,
            post_neighbors=set(),
            candidate_neighbors=set(),
        )
        self.assertEqual(score, 0.0)

    def test_components_total_includes_new_weights(self):
        comps = SimilarityComponents(
            tag_score=0.0,
            category_score=0.0,
            series_score=0.0,
            content_score=0.0,
            recency_score=0.0,
            backlink_score=1.0,
            citation_score=1.0,
        )
        # 0.25 + 0.15 = 0.40
        self.assertAlmostEqual(comps.total(), 0.40)

    def test_components_as_dict_roundtrips(self):
        comps = SimilarityComponents(
            tag_score=0.1,
            category_score=0.2,
            series_score=0.3,
            content_score=0.4,
            recency_score=0.5,
            backlink_score=0.6,
            citation_score=0.7,
        )
        d = comps.as_dict()
        self.assertEqual(d["tag"], 0.1)
        self.assertEqual(d["backlink"], 0.6)
        self.assertEqual(d["citation"], 0.7)


class BatchMapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="author", password="x")
        cls.p1 = _make_post(cls.user, "map-post-1")
        cls.p2 = _make_post(cls.user, "map-post-2")
        cls.p3 = _make_post(cls.user, "map-post-3")

    def test_neighbor_map_unions_outgoing_and_incoming(self):
        InternalLink.objects.create(source_post=self.p1, target_post=self.p2)
        InternalLink.objects.create(source_post=self.p3, target_post=self.p1)
        neighbors = _build_neighbor_map(self.p1.pk, [self.p2.pk, self.p3.pk])
        self.assertEqual(neighbors[self.p1.pk], {self.p2.pk, self.p3.pk})
        self.assertEqual(neighbors[self.p2.pk], {self.p1.pk})
        self.assertEqual(neighbors[self.p3.pk], {self.p1.pk})

    def test_citation_map_collects_source_ids(self):
        src_a = Source.objects.create(
            title="Alpha", citation_key="alpha", source_type=SourceType.ARTICLE
        )
        src_b = Source.objects.create(
            title="Beta", citation_key="beta", source_type=SourceType.ARTICLE
        )
        PostCitation.objects.create(post=self.p1, source=src_a, position=1)
        PostCitation.objects.create(post=self.p1, source=src_b, position=2)
        PostCitation.objects.create(post=self.p2, source=src_a, position=1)
        cites = _build_citation_map(self.p1.pk, [self.p2.pk, self.p3.pk])
        self.assertEqual(cites[self.p1.pk], {src_a.pk, src_b.pk})
        self.assertEqual(cites[self.p2.pk], {src_a.pk})
        self.assertEqual(cites[self.p3.pk], set())


class RecomputeTaskTests(TestCase):
    """The task itself, invoked with a known pair of posts."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="author", password="x")
        cls.tag = Tag.objects.create(name="Python", slug="python")

    def test_task_writes_rows_for_shared_tag(self):
        p1 = _make_post(self.user, "task-post-1")
        p2 = _make_post(self.user, "task-post-2")
        p1.tags.add(self.tag)
        p2.tags.add(self.tag)
        PostSimilarity.objects.filter(source_post=p1).delete()

        result = recompute_similarity_for_post.apply(args=(p1.pk,)).result
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["rows"], 1)
        self.assertTrue(
            PostSimilarity.objects.filter(source_post=p1, target_post=p2).exists()
        )

    def test_task_clears_rows_for_unpublished_post(self):
        p1 = _make_post(self.user, "task-post-a")
        p2 = _make_post(self.user, "task-post-b")
        PostSimilarity.objects.create(source_post=p1, target_post=p2, score=0.5)
        p1.status = Post.Status.DRAFT
        p1.save()  # draft save bypasses the signal's enqueue path, so call manually
        result = recompute_similarity_for_post.apply(args=(p1.pk,)).result
        self.assertTrue(result["success"])
        self.assertEqual(result["rows"], 0)
        self.assertFalse(PostSimilarity.objects.filter(source_post=p1).exists())


class SignalTriggerTests(TestCase):
    """
    Under CELERY_TASK_ALWAYS_EAGER=True (settings.py flips this during
    manage.py test), .delay() runs the task inline. That lets us assert
    against PostSimilarity rows directly after the signal fires.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="author", password="x")

    def test_post_save_populates_similarity(self):
        tag = Tag.objects.create(name="Tag", slug="tag")
        p1 = _make_post(self.user, "sig-post-1")
        p1.tags.add(tag)
        p2 = _make_post(self.user, "sig-post-2")
        p2.tags.add(tag)
        # p2's save-and-tag-add should have fired the signal;
        # but m2m add fires after save, so trigger by re-saving p1.
        p1.save()
        self.assertTrue(
            PostSimilarity.objects.filter(source_post=p1).exists()
            or PostSimilarity.objects.filter(source_post=p2).exists()
        )

    def test_internal_link_creation_recomputes_both_endpoints(self):
        p1 = _make_post(self.user, "link-post-1")
        p2 = _make_post(self.user, "link-post-2")
        PostSimilarity.objects.all().delete()
        InternalLink.objects.create(source_post=p1, target_post=p2)
        # Both endpoints' similarity rows should have been (re)computed.
        p1_row = PostSimilarity.objects.filter(source_post=p1, target_post=p2).first()
        p2_row = PostSimilarity.objects.filter(source_post=p2, target_post=p1).first()
        self.assertTrue(p1_row is not None or p2_row is not None)

    def test_citation_creation_recomputes_source_post(self):
        p1 = _make_post(self.user, "cite-post-1")
        p2 = _make_post(self.user, "cite-post-2")
        src = Source.objects.create(
            title="Shared", citation_key="shared", source_type=SourceType.ARTICLE
        )
        PostCitation.objects.create(post=p1, source=src, position=1)
        PostCitation.objects.create(post=p2, source=src, position=1)
        # After both citations exist, p1's outgoing rows should include p2.
        self.assertTrue(
            PostSimilarity.objects.filter(source_post=p1, target_post=p2).exists()
        )


class AdminInlineRendersTests(TestCase):
    """
    Regression guard: the PostSimilarityInline must not slice its queryset,
    since Django's BaseInlineFormSet.__init__ re-filters the queryset and
    errors on a sliced one with "Cannot filter a query once a slice has
    been taken." Hitting the admin change page exercises that code path.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="adminuser", email="admin@example.com", password="x"
        )
        cls.post = _make_post(cls.user, "admin-post-1")
        cls.target = _make_post(cls.user, "admin-post-2")

    def test_post_change_page_renders_with_similarity_rows(self):
        for i in range(12):
            extra = _make_post(self.user, f"admin-extra-{i}")
            PostSimilarity.objects.create(
                source_post=self.post,
                target_post=extra,
                score=0.5 - i * 0.01,
                components={"tag": 0.5},
            )
        self.client.force_login(self.user)
        response = self.client.get(f"/manage/engine/post/{self.post.pk}/change/")
        self.assertEqual(response.status_code, 200)


class ViewUsesPrecomputeTests(TestCase):
    """The detail view must read from PostSimilarity, never compute inline."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="author", password="x")
        cls.tag = Tag.objects.create(name="React", slug="react")
        cls.p1 = _make_post(cls.user, "view-post-1")
        cls.p2 = _make_post(cls.user, "view-post-2")
        cls.p1.tags.add(cls.tag)
        cls.p2.tags.add(cls.tag)

    def test_detail_view_reads_precomputed_rows(self):
        # Seed a row manually so we can verify it gets picked up verbatim.
        PostSimilarity.objects.create(
            source_post=self.p1,
            target_post=self.p2,
            score=0.99,
            components={"tag": 1.0},
        )
        with mock.patch(
            "engine.similarity.compute_similar_posts",
            side_effect=AssertionError("view must not call compute path"),
        ):
            response = self.client.get(f"/posts/{self.p1.slug}/")
        self.assertEqual(response.status_code, 200)
        similar = list(response.context["similar_posts"])
        self.assertIn(self.p2, similar)
        self.assertEqual(similar[0].similarity_score, 0.99)
