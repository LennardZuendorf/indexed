import time
import logging


def execute_with_retry(func, func_identifier, retries=3, delay=1):
    """Execute function with simple retry and basic backoff.

    - Retries on any Exception (callers should filter if needed)
    - Exponential backoff: delay * (2 ** attempt)
    - If exception exposes HTTP status 429 or Retry-After header, honor it
    """
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            logging.warning(
                f'Attempt of "{func_identifier}" number {attempt + 1} failed: {e}'
            )
            if attempt < retries - 1:
                sleep_time = delay * (2 ** attempt)
                # Try to respect rate limiting if present
                try:
                    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
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
                logging.error(f"All {retries} attempts failed.")
                raise e
