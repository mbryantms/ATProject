"""Safe outbound-fetch helpers for the bibliography subsystem.

DOI / ISBN / URL resolution and link-checking all fetch a ``Source``-supplied
URL server-side. Those URLs come from admin input and Zotero sync, so they are
untrusted. ``urllib.request.urlopen`` will happily open ``file://`` (local file
disclosure) and connect to internal/link-local addresses such as the cloud
metadata endpoint ``169.254.169.254`` (SSRF). These helpers constrain outbound
requests to http(s) hosts that resolve to public IP addresses.

This is a proportionate mitigation for a staff-gated feature: it closes the
LFI and the obvious internal-SSRF targets. It does not defend against a
determined DNS-rebinding attacker (the socket re-resolves the name), which is
out of scope for admin-triggered fetches.
"""

import ipaddress
import socket
import threading
import time
from urllib.parse import urlparse
from urllib.request import urlopen

ALLOWED_SCHEMES = {"http", "https"}

# Minimum spacing between requests to the same host. CrossRef, Open Library
# and archive.org all ask polite clients to self-throttle; the batch callers
# (link checker, Zotero resync, ISBN author lookups) otherwise fire tight
# loops at a single API host.
MIN_REQUEST_INTERVAL = 1.0

_next_slot_at: dict[str, float] = {}
_throttle_lock = threading.Lock()


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch server-side."""


def _host_is_public(hostname: str) -> bool:
    """Return True only if every A/AAAA record for *hostname* is a global IP."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Unresolvable — let the caller's urlopen raise the network error.
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def validate_public_url(url: str) -> None:
    """Raise :class:`UnsafeURLError` if *url* must not be fetched server-side."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"Refusing to fetch non-http(s) URL scheme: {parsed.scheme!r}"
        )
    if not parsed.hostname:
        raise UnsafeURLError("URL has no host")
    if not _host_is_public(parsed.hostname):
        raise UnsafeURLError(
            f"Refusing to fetch URL resolving to a non-public address: "
            f"{parsed.hostname}"
        )


def throttle_host(hostname: str) -> None:
    """Keep at least :data:`MIN_REQUEST_INTERVAL` between requests per host.

    Each caller reserves the next available slot for *hostname* under the
    lock, then sleeps outside it until that slot arrives — concurrent threads
    queue politely instead of racing. State is per-process, so parallel
    Celery workers each keep their own window; the goal is to stop tight
    single-process loops from hammering one API host, not to enforce a
    global rate.
    """
    with _throttle_lock:
        now = time.monotonic()
        ready_at = max(now, _next_slot_at.get(hostname, 0.0))
        _next_slot_at[hostname] = ready_at + MIN_REQUEST_INTERVAL
    if ready_at > now:
        time.sleep(ready_at - now)


def safe_urlopen(req, *, timeout):
    """``urlopen`` wrapper that validates and rate-limits before connecting.

    Accepts a ``urllib.request.Request`` (or a URL string) and validates its
    full URL — including the method and headers already set on the Request.
    """
    url = req.full_url if hasattr(req, "full_url") else req
    validate_public_url(url)
    throttle_host(urlparse(url).hostname.lower())
    return urlopen(req, timeout=timeout)
