"""
Link rot detection and remediation.

Checks source URLs for availability and attempts to locate archived versions
via the Wayback Machine when links are broken.
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.utils import timezone

logger = logging.getLogger(__name__)

_USER_AGENT = "ATProject/1.0 (Bibliography Link Checker)"
_TIMEOUT = 20


def check_url(url: str) -> dict:
    """
    Check a URL's availability using an HTTP HEAD request.

    Returns:
        Dict with keys: status ("ok", "redirect", "broken"), http_code, final_url.
    """
    if not url:
        return {"status": "unchecked", "http_code": None, "final_url": None}

    req = Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})

    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            code = resp.getcode()
            final_url = resp.geturl()

            if code == 200:
                status = "redirect" if final_url != url else "ok"
            elif 200 <= code < 400:
                status = "ok"
            else:
                status = "broken"

            return {
                "status": status,
                "http_code": code,
                "final_url": final_url,
            }

    except HTTPError as e:
        # Some servers reject HEAD but accept GET
        if e.code == 405:
            return _check_url_get(url)
        return {
            "status": "broken",
            "http_code": e.code,
            "final_url": None,
        }
    except URLError, TimeoutError, OSError:
        return {
            "status": "broken",
            "http_code": None,
            "final_url": None,
        }


def _check_url_get(url: str) -> dict:
    """Fallback: check URL with GET when HEAD is rejected."""
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            code = resp.getcode()
            final_url = resp.geturl()
            status = "redirect" if final_url != url else "ok"
            return {"status": status, "http_code": code, "final_url": final_url}
    except HTTPError as e:
        return {"status": "broken", "http_code": e.code, "final_url": None}
    except URLError, TimeoutError, OSError:
        return {"status": "broken", "http_code": None, "final_url": None}


def check_wayback_machine(url: str) -> str | None:
    """
    Check if the Wayback Machine has an archived snapshot of a URL.

    Returns:
        Archive URL if found, None otherwise.
    """
    api_url = f"https://archive.org/wayback/available?url={url}"
    req = Request(api_url, headers={"User-Agent": _USER_AGENT})

    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())

        snapshots = data.get("archived_snapshots", {})
        closest = snapshots.get("closest", {})

        if closest.get("available"):
            return closest.get("url")

        return None

    except Exception:
        logger.debug("Wayback Machine check failed for %s", url)
        return None


def submit_to_wayback(url: str) -> bool:
    """
    Submit a URL to the Wayback Machine's Save Page Now API.

    Returns:
        True if submission was accepted, False otherwise.
    """
    save_url = f"https://web.archive.org/save/{url}"
    req = Request(save_url, headers={"User-Agent": _USER_AGENT})

    try:
        with urlopen(req, timeout=30) as resp:
            return resp.getcode() in (200, 302)
    except Exception:
        logger.debug("Wayback Machine save failed for %s", url)
        return False


def check_source_urls(batch_size: int = 50, max_age_days: int = 7) -> dict:
    """
    Check a batch of source URLs, prioritizing oldest-checked first.

    Args:
        batch_size: Number of URLs to check in this batch.
        max_age_days: Skip URLs checked within this many days.

    Returns:
        Stats dict with checked, ok, broken, archived counts.
    """
    from engine.models import Source

    stats = {"checked": 0, "ok": 0, "redirect": 0, "broken": 0, "archived": 0}

    cutoff = timezone.now() - timezone.timedelta(days=max_age_days)

    # Get URLs to check: unchecked first, then oldest-checked
    sources = (
        Source.objects.exclude(url="")
        .filter(
            models_Q_unchecked_or_stale(cutoff),
        )
        .order_by("url_last_checked")[:batch_size]
    )

    for source in sources:
        result = check_url(source.url)
        status = result["status"]

        # If broken, check Wayback Machine
        archive_url = ""
        if status == "broken":
            archive_url = check_wayback_machine(source.url) or ""
            if archive_url:
                status = "archived"

        Source.objects.filter(pk=source.pk).update(
            url_status=status,
            url_last_checked=timezone.now(),
            url_check_count=source.url_check_count + 1,
            url_archive=archive_url or source.url_archive,
        )

        stats["checked"] += 1
        stats[status] = stats.get(status, 0) + 1

    return stats


def models_Q_unchecked_or_stale(cutoff):
    """Build a Q object for unchecked or stale URLs."""
    from django.db.models import Q

    return Q(url_last_checked__isnull=True) | Q(url_last_checked__lt=cutoff)
