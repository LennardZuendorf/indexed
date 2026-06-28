"""Origin guard for credentialed attachment fetches."""

from urllib.parse import urlsplit


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


def is_same_origin(url: str, base_url: str) -> bool:
    """Return True iff url and base_url share scheme + host (case-insensitive).

    Port is intentionally NOT compared: base URLs are often stored without an
    explicit port, and default-port attachments would be falsely skipped.
    Malformed or hostless urls return False (fail closed).
    """
    try:
        parsed = urlsplit(url)
        base = urlsplit(base_url)
    except Exception:
        return False

    if not parsed.hostname or not base.hostname:
        return False

    return (
        parsed.scheme.lower() == base.scheme.lower()
        and parsed.hostname.lower() == base.hostname.lower()
    )
