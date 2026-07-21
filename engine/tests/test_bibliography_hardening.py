"""
Tests for the Tier-5 hardening pass:

- Per-host request throttling in the shared safe_urlopen helper
- link_checker internals (HEAD/GET fallback, Wayback lookup, batch selection)
- zotero_sync internals (create/update/collision, pagination, sync version)
- Metadata resolver fetching and CSL mapping
- Celery time limits on every bibliography task
"""

import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from engine.bibliography import link_checker, net
from engine.bibliography.metadata_resolvers import (
    apply_metadata_to_source,
    resolve_doi,
    resolve_isbn,
    resolve_url,
)
from engine.bibliography.zotero_sync import (
    _update_source_from_csl,
    get_zotero_client,
    sync_zotero_library,
)
from engine.models import SiteSettings, Source


class _FakeResponse:
    """Stand-in for the context manager safe_urlopen returns."""

    def __init__(self, *, code=200, url="", body=b""):
        self._code = code
        self._url = url
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self._code

    def geturl(self):
        return self._url

    def read(self):
        return self._body


def _json_response(payload):
    return _FakeResponse(body=json.dumps(payload).encode())


class _FakeClock:
    def __init__(self, start=100.0):
        self.now = start
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ThrottleTests(TestCase):
    def setUp(self):
        net._next_slot_at.clear()
        self.addCleanup(net._next_slot_at.clear)

    def test_same_host_spaced_by_min_interval(self):
        clock = _FakeClock()
        with patch.object(net, "time", clock):
            net.throttle_host("api.crossref.org")
            net.throttle_host("api.crossref.org")
        self.assertEqual(clock.sleeps, [net.MIN_REQUEST_INTERVAL])

    def test_different_hosts_not_delayed(self):
        clock = _FakeClock()
        with patch.object(net, "time", clock):
            net.throttle_host("api.crossref.org")
            net.throttle_host("openlibrary.org")
        self.assertEqual(clock.sleeps, [])

    def test_spacing_accumulates_across_a_burst(self):
        clock = _FakeClock()
        with patch.object(net, "time", clock):
            for _ in range(3):
                net.throttle_host("web.archive.org")
        self.assertEqual(
            clock.sleeps, [net.MIN_REQUEST_INTERVAL, net.MIN_REQUEST_INTERVAL]
        )

    def test_safe_urlopen_throttles_by_hostname(self):
        with (
            patch.object(net, "_host_is_public", return_value=True),
            patch.object(net, "throttle_host") as mock_throttle,
            patch.object(net, "urlopen") as mock_open,
        ):
            net.safe_urlopen("https://API.CrossRef.org/works/x", timeout=5)
        mock_throttle.assert_called_once_with("api.crossref.org")
        mock_open.assert_called_once()


@patch("engine.bibliography.link_checker.safe_urlopen")
class CheckUrlTests(TestCase):
    URL = "https://example.com/paper"

    def test_ok(self, mock_open):
        mock_open.return_value = _FakeResponse(code=200, url=self.URL)
        result = link_checker.check_url(self.URL)
        self.assertEqual(
            result, {"status": "ok", "http_code": 200, "final_url": self.URL}
        )

    def test_redirect_detected_from_final_url(self, mock_open):
        mock_open.return_value = _FakeResponse(
            code=200, url="https://example.com/moved"
        )
        self.assertEqual(link_checker.check_url(self.URL)["status"], "redirect")

    def test_http_error_is_broken(self, mock_open):
        mock_open.side_effect = HTTPError(self.URL, 404, "Not Found", None, None)
        result = link_checker.check_url(self.URL)
        self.assertEqual(result["status"], "broken")
        self.assertEqual(result["http_code"], 404)

    def test_head_rejected_falls_back_to_get(self, mock_open):
        mock_open.side_effect = [
            HTTPError(self.URL, 405, "Method Not Allowed", None, None),
            _FakeResponse(code=200, url=self.URL),
        ]
        result = link_checker.check_url(self.URL)
        self.assertEqual(result["status"], "ok")
        head_req, get_req = (c.args[0] for c in mock_open.call_args_list)
        self.assertEqual(head_req.get_method(), "HEAD")
        self.assertEqual(get_req.get_method(), "GET")

    def test_network_error_is_broken(self, mock_open):
        mock_open.side_effect = URLError("dns failure")
        result = link_checker.check_url(self.URL)
        self.assertEqual(
            result, {"status": "broken", "http_code": None, "final_url": None}
        )

    def test_empty_url_unchecked(self, mock_open):
        self.assertEqual(link_checker.check_url("")["status"], "unchecked")
        mock_open.assert_not_called()


@patch("engine.bibliography.link_checker.safe_urlopen")
class WaybackTests(TestCase):
    def test_snapshot_found(self, mock_open):
        snapshot = "http://web.archive.org/web/2026/https://example.com"
        mock_open.return_value = _json_response(
            {"archived_snapshots": {"closest": {"available": True, "url": snapshot}}}
        )
        self.assertEqual(
            link_checker.check_wayback_machine("https://example.com"), snapshot
        )

    def test_no_snapshot(self, mock_open):
        mock_open.return_value = _json_response({"archived_snapshots": {}})
        self.assertIsNone(link_checker.check_wayback_machine("https://example.com"))

    def test_api_error_returns_none(self, mock_open):
        mock_open.side_effect = URLError("down")
        self.assertIsNone(link_checker.check_wayback_machine("https://example.com"))

    def test_submit_accepted(self, mock_open):
        mock_open.return_value = _FakeResponse(code=200)
        self.assertTrue(link_checker.submit_to_wayback("https://example.com"))

    def test_submit_failure(self, mock_open):
        mock_open.side_effect = URLError("rate limited")
        self.assertFalse(link_checker.submit_to_wayback("https://example.com"))


class CheckSourceUrlsBatchTests(TestCase):
    def setUp(self):
        # Source post_save enqueues Wayback archival for sources with URLs.
        patcher = patch("engine.bibliography.tasks.archive_source_url")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _source(self, key, url, checked_at=None):
        source = Source.objects.create(citation_key=key, title=key, url=url)
        if checked_at is not None:
            Source.objects.filter(pk=source.pk).update(url_last_checked=checked_at)
        return source

    @patch("engine.bibliography.link_checker.check_url")
    def test_never_checked_sources_take_priority(self, mock_check):
        mock_check.return_value = {"status": "ok", "http_code": 200, "final_url": None}
        stale = self._source(
            "stale2026",
            "https://example.com/stale",
            checked_at=timezone.now() - timezone.timedelta(days=30),
        )
        never = self._source("never2026", "https://example.com/never")

        stats = link_checker.check_source_urls(batch_size=1)

        self.assertEqual(stats["checked"], 1)
        never.refresh_from_db()
        stale.refresh_from_db()
        self.assertIsNotNone(never.url_last_checked)
        self.assertEqual(never.url_check_count, 1)
        self.assertEqual(stale.url_check_count, 0)

    @patch("engine.bibliography.link_checker.check_url")
    def test_recently_checked_sources_skipped(self, mock_check):
        self._source(
            "fresh2026", "https://example.com/fresh", checked_at=timezone.now()
        )
        stats = link_checker.check_source_urls(max_age_days=7)
        self.assertEqual(stats["checked"], 0)
        mock_check.assert_not_called()

    @patch("engine.bibliography.link_checker.check_wayback_machine")
    @patch("engine.bibliography.link_checker.check_url")
    def test_broken_url_promoted_to_archived(self, mock_check, mock_wayback):
        snapshot = "https://web.archive.org/web/2026/https://example.com/gone"
        mock_check.return_value = {
            "status": "broken",
            "http_code": 404,
            "final_url": None,
        }
        mock_wayback.return_value = snapshot
        source = self._source("broken2026", "https://example.com/gone")

        stats = link_checker.check_source_urls()

        source.refresh_from_db()
        self.assertEqual(source.url_status, "archived")
        self.assertEqual(source.url_archive, snapshot)
        self.assertEqual(source.url_check_count, 1)
        self.assertEqual(stats["archived"], 1)
        self.assertEqual(stats["broken"], 0)

    @patch("engine.bibliography.link_checker.check_wayback_machine")
    @patch("engine.bibliography.link_checker.check_url")
    def test_broken_url_without_snapshot_stays_broken(self, mock_check, mock_wayback):
        mock_check.return_value = {
            "status": "broken",
            "http_code": 404,
            "final_url": None,
        }
        mock_wayback.return_value = None
        source = self._source("gone2026", "https://example.com/vanished")

        stats = link_checker.check_source_urls()

        source.refresh_from_db()
        self.assertEqual(source.url_status, "broken")
        self.assertEqual(source.url_archive, "")
        self.assertEqual(stats["broken"], 1)


class _FakeZotero:
    """Minimal pyzotero stand-in: paginated top(), follow(), version."""

    def __init__(self, pages, version=42):
        self._pages = list(pages)
        self.links = {}
        self.top_kwargs = None
        self._version = version

    def _next_page(self):
        page = self._pages.pop(0)
        self.links = {"next": "cursor"} if self._pages else {}
        return page

    def top(self, **kwargs):
        self.top_kwargs = kwargs
        return self._next_page()

    def follow(self):
        return self._next_page()

    def last_modified_version(self):
        return self._version

    def children(self, key):
        return []


def _csl(item_id, title, family="Smith", year=2024, **extra):
    item = {
        "id": item_id,
        "type": "article-journal",
        "title": title,
        "author": [{"family": family, "given": "Ann"}],
        "issued": {"date-parts": [[year]]},
    }
    item.update(extra)
    return item


class ZoteroSyncTests(TestCase):
    def setUp(self):
        cache.delete("site_settings")
        self.addCleanup(cache.delete, "site_settings")
        patcher = patch("engine.bibliography.tasks.archive_source_url")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _sync(self, pages, version=42, **sync_kwargs):
        fake = _FakeZotero(pages, version=version)
        with patch(
            "engine.bibliography.zotero_sync.get_zotero_client", return_value=fake
        ):
            stats = sync_zotero_library(**sync_kwargs)
        return fake, stats

    def _stored_version(self):
        return SiteSettings.objects.get(pk=1).zotero_last_sync_version

    def test_full_sync_creates_sources_and_records_version(self):
        fake, stats = self._sync(
            [
                {
                    "items": [
                        _csl("Z1", "Quantum Widgets", DOI="10.1/qw"),
                        _csl("Z2", "Classical Widgets", family="Jones"),
                    ]
                }
            ]
        )
        self.assertEqual(stats["created"], 2)
        self.assertEqual(stats["errors"], 0)
        z1 = Source.objects.get(zotero_key="Z1")
        self.assertEqual(z1.title, "Quantum Widgets")
        self.assertEqual(z1.source_type, "article-journal")
        self.assertEqual(z1.doi, "10.1/qw")
        self.assertTrue(z1.citation_key)
        self.assertEqual(self._stored_version(), 42)
        self.assertIsNotNone(SiteSettings.objects.get(pk=1).zotero_last_sync_at)

    def test_incremental_sync_passes_since_version(self):
        settings_obj = SiteSettings.load()
        settings_obj.zotero_last_sync_version = 10
        settings_obj.save()
        fake, _ = self._sync([{"items": []}])
        self.assertEqual(fake.top_kwargs.get("since"), 10)

    def test_full_sync_ignores_since_version(self):
        settings_obj = SiteSettings.load()
        settings_obj.zotero_last_sync_version = 10
        settings_obj.save()
        fake, _ = self._sync([{"items": []}], full=True)
        self.assertNotIn("since", fake.top_kwargs)

    def test_pagination_follows_next_links(self):
        _, stats = self._sync(
            [
                {"items": [_csl("Z1", "Page One")]},
                {"items": [_csl("Z2", "Page Two", family="Jones")]},
            ]
        )
        self.assertEqual(stats["created"], 2)
        self.assertTrue(Source.objects.filter(zotero_key="Z2").exists())

    def test_colliding_citation_keys_get_distinct_suffixes(self):
        _, stats = self._sync(
            [{"items": [_csl("Z1", "Same Title"), _csl("Z2", "Same Title")]}]
        )
        self.assertEqual(stats["created"], 2)
        keys = set(
            Source.objects.filter(zotero_key__in=["Z1", "Z2"]).values_list(
                "citation_key", flat=True
            )
        )
        self.assertEqual(len(keys), 2)

    def test_existing_source_updated_but_citation_key_preserved(self):
        Source.objects.create(
            citation_key="handpicked99", title="Old Title", zotero_key="Z1"
        )
        _, stats = self._sync([{"items": [_csl("Z1", "New Title")]}])
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["created"], 0)
        source = Source.objects.get(zotero_key="Z1")
        self.assertEqual(source.citation_key, "handpicked99")
        self.assertEqual(source.title, "New Title")

    def test_dry_run_saves_nothing(self):
        _, stats = self._sync(
            [{"items": [_csl("Z1", "Quantum Widgets")]}], dry_run=True
        )
        self.assertEqual(stats["created"], 1)
        self.assertFalse(Source.all_objects.filter(zotero_key="Z1").exists())
        self.assertEqual(self._stored_version(), 0)

    def test_fetch_failure_recorded_and_version_not_advanced(self):
        class _BrokenZotero(_FakeZotero):
            def top(self, **kwargs):
                raise RuntimeError("zotero 500")

        fake = _BrokenZotero([])
        with patch(
            "engine.bibliography.zotero_sync.get_zotero_client", return_value=fake
        ):
            stats = sync_zotero_library()
        self.assertEqual(stats["errors"], 1)
        self.assertTrue(stats["error_details"])
        self.assertEqual(self._stored_version(), 0)

    def test_item_error_does_not_abort_sync_but_blocks_version(self):
        _, stats = self._sync([{"items": ["junk", _csl("Z1", "Good Item")]}])
        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(self._stored_version(), 0)

    def test_update_source_from_csl_maps_fields(self):
        source = Source()
        csl_item = {
            "id": "Z9",
            "type": "book",
            "title": "Deep Fields",
            "author": [{"family": "Ng", "given": "Kim"}],
            "container-title": "Anthology",
            "publisher": "Pressly",
            "issued": {"date-parts": [[2020, 5]]},
            "DOI": "10.1/x",
            "URL": "https://example.com/b",
            "abstract": "About things.",
            "language": "de",
        }
        _update_source_from_csl(source, csl_item)
        self.assertEqual(source.source_type, "book")
        self.assertEqual(source.container_title, "Anthology")
        self.assertEqual(source.publisher, "Pressly")
        self.assertEqual(source.issued_date, {"date-parts": [[2020, 5]]})
        self.assertEqual(source.doi, "10.1/x")
        self.assertEqual(source.language, "de")
        self.assertEqual(source.csl_json, csl_item)

    def test_unconfigured_client_raises(self):
        SiteSettings.load()  # Default row: no library id or API key.
        with self.assertRaises(ValueError):
            get_zotero_client()


@patch("engine.bibliography.metadata_resolvers.safe_urlopen")
class ResolveDoiTests(TestCase):
    def test_crossref_payload_mapped_to_csl(self, mock_open):
        mock_open.return_value = _json_response(
            {
                "message": {
                    "type": "journal-article",
                    "title": ["Entangled Widgets"],
                    "DOI": "10.1234/widgets",
                    "author": [
                        {"family": "Smith", "given": "Ann"},
                        {"name": "The Widget Consortium"},
                    ],
                    "container-title": ["Journal of Widgetry"],
                    "publisher": "Widget Press",
                    "volume": "12",
                    "issue": "3",
                    "page": "45-67",
                    "issued": {"date-parts": [[2024, 6]]},
                    "URL": "https://doi.org/10.1234/widgets",
                    "ISSN": ["1234-5678", "8765-4321"],
                    "abstract": "<jats:p>Widgets are entangled.</jats:p>",
                }
            }
        )
        csl = resolve_doi("https://doi.org/10.1234/widgets")
        self.assertEqual(csl["type"], "article-journal")
        self.assertEqual(csl["title"], "Entangled Widgets")
        self.assertEqual(
            csl["author"],
            [{"family": "Smith", "given": "Ann"}, {"literal": "The Widget Consortium"}],
        )
        self.assertEqual(csl["container-title"], "Journal of Widgetry")
        self.assertEqual(csl["page"], "45-67")
        self.assertEqual(csl["issued"], {"date-parts": [[2024, 6]]})
        self.assertEqual(csl["ISSN"], "1234-5678")
        self.assertEqual(csl["abstract"], "Widgets are entangled.")
        request = mock_open.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://api.crossref.org/works/10.1234/widgets"
        )

    def test_fetch_failure_returns_none(self, mock_open):
        mock_open.side_effect = URLError("crossref down")
        self.assertIsNone(resolve_doi("10.1234/widgets"))


@patch("engine.bibliography.metadata_resolvers.safe_urlopen")
class ResolveIsbnTests(TestCase):
    def test_open_library_book_with_author_lookup(self, mock_open):
        mock_open.side_effect = [
            _json_response(
                {
                    "title": "Widget Theory",
                    "publishers": ["Widget House"],
                    "publish_date": "May 2019",
                    "number_of_pages": 320,
                    "authors": [{"key": "/authors/OL1A"}],
                }
            ),
            _json_response({"name": "Ann van Smith"}),
        ]
        csl = resolve_isbn("978-1-23456-789-0")
        self.assertEqual(csl["type"], "book")
        self.assertEqual(csl["title"], "Widget Theory")
        self.assertEqual(csl["publisher"], "Widget House")
        self.assertEqual(csl["issued"], {"date-parts": [[2019]]})
        self.assertEqual(csl["number-of-pages"], "320")
        self.assertEqual(csl["author"], [{"given": "Ann van", "family": "Smith"}])
        book_req = mock_open.call_args_list[0].args[0]
        self.assertEqual(
            book_req.full_url, "https://openlibrary.org/isbn/9781234567890.json"
        )

    def test_author_lookup_failure_tolerated(self, mock_open):
        mock_open.side_effect = [
            _json_response({"title": "Widget Theory", "authors": [{"key": "/a/OL1A"}]}),
            URLError("author api down"),
        ]
        csl = resolve_isbn("9781234567890")
        self.assertEqual(csl["title"], "Widget Theory")
        self.assertNotIn("author", csl)


_OG_HTML = b"""<html><head>
<title>Fallback Title</title>
<meta property="og:title" content="Widget Post">
<meta property="og:site_name" content="Widget Blog">
<meta property="og:description" content="A post about widgets.">
<meta name="author" content="Ann Smith">
<meta property="article:published_time" content="2025-03-09T10:00:00Z">
</head><body></body></html>"""


@patch("engine.bibliography.metadata_resolvers.safe_urlopen")
class ResolveUrlTests(TestCase):
    def test_opengraph_metadata_extracted(self, mock_open):
        mock_open.return_value = _FakeResponse(body=_OG_HTML)
        csl = resolve_url("https://blog.example.com/widgets")
        self.assertEqual(csl["type"], "webpage")
        self.assertEqual(csl["title"], "Widget Post")
        self.assertEqual(csl["container-title"], "Widget Blog")
        self.assertEqual(csl["abstract"], "A post about widgets.")
        self.assertEqual(csl["author"], [{"given": "Ann", "family": "Smith"}])
        self.assertEqual(csl["issued"], {"date-parts": [[2025, 3, 9]]})
        self.assertIn("accessed", csl)

    def test_github_url_typed_as_software(self, mock_open):
        mock_open.return_value = _FakeResponse(
            body=b"<html><head><title>repo</title></head></html>"
        )
        csl = resolve_url("https://github.com/example/widgets")
        self.assertEqual(csl["type"], "software")

    def test_fetch_failure_returns_none(self, mock_open):
        mock_open.side_effect = URLError("timeout")
        self.assertIsNone(resolve_url("https://example.com/x"))


class ApplyMetadataTests(TestCase):
    def test_only_empty_fields_filled(self):
        source = Source(citation_key="apply2026", title="Hand-written Title")
        updated = apply_metadata_to_source(
            source,
            {
                "title": "Fetched Title",
                "publisher": "Fetched Press",
                "DOI": "10.1/z",
            },
        )
        self.assertEqual(source.title, "Hand-written Title")
        self.assertEqual(source.publisher, "Fetched Press")
        self.assertEqual(source.doi, "10.1/z")
        self.assertEqual(sorted(updated), ["doi", "publisher"])


class TaskTimeLimitTests(TestCase):
    def test_every_bibliography_task_has_time_limits(self):
        from engine.bibliography import tasks as bib_tasks

        for task in (
            bib_tasks.sync_zotero_library,
            bib_tasks.check_source_urls_task,
            bib_tasks.archive_source_url,
            bib_tasks.extract_source_file_text,
            bib_tasks.fetch_metadata_for_source,
            bib_tasks.check_source_urls_for_ids,
            bib_tasks.resync_zotero_sources,
        ):
            with self.subTest(task=task.name):
                self.assertIsNotNone(task.soft_time_limit)
                self.assertIsNotNone(task.time_limit)
                self.assertGreater(task.time_limit, task.soft_time_limit)
