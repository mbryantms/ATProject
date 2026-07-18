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
from urllib.parse import urlparse
from urllib.request import urlopen

ALLOWED_SCHEMES = {"http", "https"}


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


def safe_urlopen(req, *, timeout):
    """``urlopen`` wrapper that validates the target before connecting.

    Accepts a ``urllib.request.Request`` (or a URL string) and validates its
    full URL — including the method and headers already set on the Request.
    """
    url = req.full_url if hasattr(req, "full_url") else req
    validate_public_url(url)
    return urlopen(req, timeout=timeout)
