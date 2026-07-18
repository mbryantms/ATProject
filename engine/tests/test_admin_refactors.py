"""
Tests for the admin-review refactors that moved behavior into the model/service
layer or changed workflows: publish provenance, usage-count reconciliation
signals, asset key/thumbnail helpers, and the async Source actions.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from engine.models import Asset, Post, PostAsset, Source, Tag

User = get_user_model()


class PublishProvenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="a", password="p")

    def _draft(self, slug):
        return Post.objects.create(
            title=slug,
            slug=slug,
            author=self.user,
            status=Post.Status.DRAFT,
            content_markdown="x",
        )

    def test_publish_stamps_status_time_and_publisher(self):
        post = self._draft("d1")
        self.assertIsNone(post.published_at)
        post.publish(by=self.user)
        post.refresh_from_db()
        self.assertEqual(post.status, Post.Status.PUBLISHED)
        self.assertIsNotNone(post.published_at)
        self.assertEqual(post.published_by_id, self.user.id)

    def test_publish_by_recorded_only_once(self):
        post = self._draft("d2")
        post.publish(by=self.user)
        first_time = post.published_at
        other = User.objects.create_user(username="b", password="p")
        post.publish(by=other)  # already published
        post.refresh_from_db()
        self.assertEqual(post.published_by_id, self.user.id)  # unchanged
        self.assertEqual(post.published_at, first_time)  # unchanged

    def test_save_autostamps_published_at(self):
        # A bare status change (no admin) must still get a go-live time so the
        # DB CheckConstraint holds and it shows on the site.
        post = self._draft("d3")
        post.status = Post.Status.PUBLISHED
        post.save()
        post.refresh_from_db()
        self.assertIsNotNone(post.published_at)


class UsageCountSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="u", password="p")
        cls.post = Post.objects.create(
            title="p", slug="p", author=cls.user, content_markdown="x"
        )

    def test_tag_usage_count_tracks_membership(self):
        tag = Tag.objects.create(name="t1", slug="t1")
        self.assertEqual(Tag.objects.get(pk=tag.pk).usage_count, 0)
        self.post.tags.add(tag)
        self.assertEqual(Tag.objects.get(pk=tag.pk).usage_count, 1)
        self.post.tags.remove(tag)
        self.assertEqual(Tag.objects.get(pk=tag.pk).usage_count, 0)

    def test_tag_usage_count_on_clear(self):
        tag = Tag.objects.create(name="t2", slug="t2")
        self.post.tags.add(tag)
        self.assertEqual(Tag.objects.get(pk=tag.pk).usage_count, 1)
        self.post.tags.clear()
        self.assertEqual(Tag.objects.get(pk=tag.pk).usage_count, 0)

    def test_asset_usage_count_tracks_postasset(self):
        asset = Asset.objects.create(
            title="img", asset_type="image", alt_text="a", status="ready"
        )
        self.assertEqual(Asset.all_objects.get(pk=asset.pk).usage_count, 0)
        pa = PostAsset.objects.create(post=self.post, asset=asset)
        self.assertEqual(Asset.all_objects.get(pk=asset.pk).usage_count, 1)
        pa.delete()
        self.assertEqual(Asset.all_objects.get(pk=asset.pk).usage_count, 0)


class AssetKeyPreviewTests(TestCase):
    def test_preview_key_matches_prefix_scheme(self):
        a = Asset(title="My Great Photo", asset_type="image")
        self.assertEqual(a.preview_key(), "img-my-great-photo")
        v = Asset(title="Clip", asset_type="video")
        self.assertEqual(v.preview_key(), "vid-clip")

    def test_thumbnail_url_falls_back_to_original_without_renditions(self):
        a = Asset(title="x", asset_type="image")
        # No file, no renditions -> empty string (no crash).
        self.assertEqual(a.thumbnail_url(), "")

    def test_thumbnail_url_non_image_returns_file_or_empty(self):
        a = Asset(title="doc", asset_type="document")
        self.assertEqual(a.thumbnail_url(), "")


class SourceAsyncActionTests(TestCase):
    """The bulk Source actions queue Celery tasks instead of blocking."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin", password="pw", email="a@example.com"
        )
        cls.source = Source.objects.create(
            citation_key="smith2024",
            title="A paper",
            source_type="article",
            doi="10.1/x",
            url="https://example.com/paper",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _run_action(self, action):
        return self.client.post(
            "/manage/engine/source/",
            {"action": action, "_selected_action": [str(self.source.pk)]},
            follow=True,
        )

    def test_doi_fetch_queues_task(self):
        with mock.patch(
            "engine.bibliography.tasks.fetch_metadata_for_source.delay"
        ) as m:
            resp = self._run_action("fetch_metadata_from_doi")
        self.assertEqual(resp.status_code, 200)
        m.assert_called_once_with(self.source.pk, "doi")

    def test_check_urls_queues_batch_task(self):
        with mock.patch(
            "engine.bibliography.tasks.check_source_urls_for_ids.delay"
        ) as m:
            resp = self._run_action("check_urls")
        self.assertEqual(resp.status_code, 200)
        m.assert_called_once()
        # called with the list of selected ids
        self.assertIn(self.source.pk, m.call_args[0][0])
