import time

from loguru import logger

TRANSIENT_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def is_transient_http_error(exc: BaseException) -> bool:
    """Return True if exc represents a transient HTTP or network failure."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status is not None:
        return int(status) in TRANSIENT_HTTP_STATUS
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


def execute_with_retry(func, func_identifier, retries=3, delay=1):
    """Execute function with simple retry and basic backoff.

    - Retries only on transient HTTP errors (429, 5xx) or network failures
    - Re-raises permanent HTTP errors (401, 404, etc.) immediately
    - Exponential backoff: delay * (2 ** attempt)
    - If exception exposes HTTP status 429 or Retry-After header, honor it
    """
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            if not is_transient_http_error(e):
                raise

            logger.warning(
                f'Attempt of "{func_identifier}" number {attempt + 1} failed: {e}'
            )
            if attempt < retries - 1:
                sleep_time = delay * (2**attempt)
                # Try to respect rate limiting if present
                try:
                    status = getattr(e, "status_code", None) or getattr(
                        getattr(e, "response", None), "status_code", None
                    )
                    if status == 429:
                        retry_after = None
                        resp = getattr(e, "response", None)
                        if resp is not None:
                            headers = getattr(resp, "headers", {}) or {}
                            retry_after = headers.get("Retry-After")
                        if retry_after is not None:
                            try:
                                sleep_time = max(float(retry_after), sleep_time)
                            except Exception:
                                pass
                except Exception:
                    pass
                time.sleep(sleep_time)
            else:
                logger.error(f"All {retries} attempts failed.")
                raise e
