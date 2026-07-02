"""Origin guard for credentialed attachment fetches."""

from urllib.parse import urlsplit, SplitResult


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


def is_same_origin(url: str, base_url: str) -> bool:
    """Return True iff url and base_url share scheme + host + effective port.

    Ports are normalized to the scheme default (443 for HTTPS, 80 for HTTP), so a
    base URL stored without an explicit port still matches a default-port
    attachment, while a non-default port (e.g. ``:8443``) is treated as a
    different origin — credentials must not leak to a different service on the
    same host. Malformed or hostless urls return False (fail closed).
    """
    try:
        parsed = urlsplit(url)
        base = urlsplit(base_url)
    except Exception:
        return False

    if not parsed.hostname or not base.hostname or not parsed.scheme or not base.scheme:
        return False

    return (
        parsed.scheme.lower() == base.scheme.lower()
        and parsed.hostname.lower() == base.hostname.lower()
        and _effective_port(parsed) == _effective_port(base)
    )
