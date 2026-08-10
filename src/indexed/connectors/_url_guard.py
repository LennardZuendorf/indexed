"""Origin guard for credentialed attachment fetches."""

import re
from urllib.parse import SplitResult, urlsplit


def warn_if_off_origin(url: str, base_url: str) -> bool:
    """Return True if same-origin; log a warning and return False otherwise.

    Drop-in guard for credentialed attachment fetchers: call before issuing any
    request that carries auth headers.
    """
    if is_same_origin(url, base_url):
        return True
    from loguru import logger

    logger.warning(
        f"Skipping off-origin attachment; refusing to send credentials to: {url}"
    )
    return False


def _effective_port(parts: SplitResult) -> int | None:
    """Return the port for parts, normalizing a missing port to the scheme default.

    HTTPS defaults to 443, HTTP to 80. Returns None for any other scheme or an
    out-of-range / non-numeric port (which fails the comparison closed).
    """
    try:
        if parts.port is not None:
            return parts.port
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return None


def _host_without_port(userinfo_stripped: str) -> str:
    """Drop a trailing ``:port`` from a host, bracket-aware for IPv6.

    An IPv6 host is wrapped in brackets (``[::1]:8080``) precisely so the
    colons inside the address aren't mistaken for the port delimiter; a naive
    ``split(":", 1)[0]`` instead cuts at the *first* colon and collapses every
    bracketed IPv6 host down to the literal ``"["``, making distinct hosts
    (``[::1]`` vs ``[::2]``) indistinguishable.
    """
    if userinfo_stripped.startswith("["):
        end = userinfo_stripped.find("]")
        if end != -1:
            return userinfo_stripped[: end + 1]
    return userinfo_stripped.split(":", 1)[0]


def _client_host(url: str) -> str | None:
    """Extract the host the way the actual HTTP client (requests/urllib3) does.

    ``urllib.parse.urlsplit`` follows RFC 3986 and does not treat a backslash
    as an authority delimiter, but urllib3 does — so for an authority like
    ``evil.com\\@good.com``, ``urlsplit`` reports host ``good.com`` while the
    real request is sent to ``evil.com`` (C3: the parser differential a
    same-origin check must not trust). Mirror urllib3's split: cut the
    authority at the first of ``/ ? # \\`` after ``scheme://``, take the host
    after the last ``@`` (drop credentials), then drop the port — bracket-aware
    for IPv6 — and normalize a legitimate trailing FQDN dot (``good.com.`` ==
    ``good.com``).
    """
    if "://" not in url:
        return None
    rest = url.split("://", 1)[-1]
    authority = re.split(r"[/?#\\]", rest, maxsplit=1)[0]
    if not authority:
        return None
    host = _host_without_port(authority.rsplit("@", 1)[-1]).strip()
    return host.rstrip(".").lower() or None


def is_cloud_host(url: str) -> bool:
    """Return True iff ``url``'s *host* is an Atlassian Cloud (``*.atlassian.net``) domain.

    The host is extracted (via :func:`_client_host`, the same authority parse the
    HTTP client uses) *before* the suffix check, so a raw-URL substring such as
    ``https://evil.com/x.atlassian.net`` does not match — closing the incomplete
    URL-substring sanitization hole that a bare ``url.endswith(".atlassian.net")``
    leaves open. A scheme-less value (``company.atlassian.net``) is treated as a
    bare host for backwards compatibility. Empty/hostless input returns False
    (fail closed).
    """
    normalized = url.strip().rstrip("/")
    host = _client_host(normalized)
    if host is None:
        # No scheme — treat the leading authority segment as a bare host.
        authority = re.split(r"[/?#\\]", normalized, maxsplit=1)[0]
        host = authority.rsplit("@", 1)[-1].split(":", 1)[0].rstrip(".").lower()
    return host.endswith(".atlassian.net")


def is_same_origin(url: str, base_url: str) -> bool:
    """Return True iff url and base_url share scheme + host + effective port.

    Host comparison uses ``_client_host``, which parses the authority the same
    way the HTTP client does (C3) rather than ``urlsplit``'s RFC-3986 view —
    otherwise the guard can approve a URL whose credentials the client actually
    routes to a different (attacker) host. Ports are normalized to the scheme
    default (443 for HTTPS, 80 for HTTP), so a base URL stored without an
    explicit port still matches a default-port attachment, while a non-default
    port (e.g. ``:8443``) is treated as a different origin. Malformed or
    hostless urls return False (fail closed).
    """
    try:
        parsed = urlsplit(url)
        base = urlsplit(base_url)
    except Exception:
        return False

    if not parsed.scheme or not base.scheme:
        return False

    client_host = _client_host(url)
    base_host = _client_host(base_url)
    if not client_host or not base_host:
        return False

    return (
        parsed.scheme.lower() == base.scheme.lower()
        and client_host == base_host
        and _effective_port(parsed) == _effective_port(base)
    )
