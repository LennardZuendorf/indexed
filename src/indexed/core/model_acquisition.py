"""Bounded, categorized acquisition of embedding models from the HuggingFace Hub.

One seam both engines share: ``core.v1``'s ``model_manager`` and ``core.v2``'s
``embedding.local`` call :func:`acquire_with_retry` so a failed download/load
becomes ONE actionable :class:`~indexed.core.errors.ModelAcquisitionError`
instead of dependency retry chatter. Pure stdlib + ``indexed.utils.retry`` —
no heavy ML import, and no v1/v2 coupling (``core.v2`` may not import
``core.v1``).

Retry contract: a transient failure (network / HTTP 429) is retried up to
``MAX_ATTEMPTS`` times with exponential backoff, so an acquisition attempt
terminates deterministically. Permanent failures (missing repo, auth/gated)
fail immediately. Every retry is logged at DEBUG, so ``--debug`` retains the
timeline while the default surface shows only the final diagnostic. Token-like
secrets are redacted from any cause text carried into a message or log.
"""

from __future__ import annotations

import re
import time
from typing import Callable, TypeVar

from loguru import logger

from indexed.core.errors import ModelAcquisitionError
from indexed.utils.retry import is_transient_http_error

T = TypeVar("T")

#: Failure categories (drive the remedy chosen by ``ModelAcquisitionError``).
NETWORK = "network"
RATE_LIMIT = "rate_limit"
AUTH = "auth"
MISSING = "missing"
#: A local cache that is present but cannot be read/loaded (re-download needed).
CORRUPT = "corrupt"
UNKNOWN = "unknown"

#: Documented retry budget for one acquisition attempt (see module docstring).
MAX_ATTEMPTS = 3
#: Exponential backoff base in seconds (1s, 2s, ... between attempts).
BASE_DELAY_SECONDS = 1.0
#: Longest redacted root-cause snippet carried into the final diagnostic.
_MAX_CAUSE_CHARS = 200

_RETRYABLE = frozenset({NETWORK, RATE_LIMIT})
_AUTH_STATUS = frozenset({401, 403})
_MISSING_NAMES = (
    "RepositoryNotFoundError",
    "EntryNotFoundError",
    "RevisionNotFoundError",
    "LocalEntryNotFoundError",
)
_SECRET_PATTERNS = (
    (re.compile(r"hf_[A-Za-z0-9]{10,}"), "hf_***"),
    (
        re.compile(
            r"(?i)\b(authorization|api[_-]?key|token|password|secret)\b"
            r"\s*[:=]\s*(?:bearer\s+)?\S+"
        ),
        r"\1=***",
    ),
    (re.compile(r"//[^/\s@]+@"), "//***@"),
)

_sleep: Callable[[float], None] = time.sleep


def redact(text: str) -> str:
    """Strip token-shaped secrets (HF tokens, auth headers, URL creds)."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def cause_summary(exc: BaseException) -> str:
    """A single redacted, length-capped line describing the root cause."""
    raw = str(exc).strip()
    first_line = raw.splitlines()[0] if raw else type(exc).__name__
    return redact(first_line)[:_MAX_CAUSE_CHARS]


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def categorize(exc: BaseException) -> str:
    """Classify an acquisition failure into a remedy-bearing category."""
    name = type(exc).__name__
    if "GatedRepo" in name:
        return AUTH
    if any(marker in name for marker in _MISSING_NAMES):
        return MISSING
    status = _status_code(exc)
    if status == 429:
        return RATE_LIMIT
    if status in _AUTH_STATUS:
        return AUTH
    if status == 404:
        return MISSING
    if is_transient_http_error(exc):
        return NETWORK
    return UNKNOWN


def is_retryable(category: str) -> bool:
    """True when the category is worth another attempt within the budget."""
    return category in _RETRYABLE


def _retry_after_seconds(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("Retry-After")
    except Exception:  # noqa: BLE001 - a malformed header must not mask the error
        return None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def acquisition_error(
    exc: BaseException,
    *,
    model_name: str,
    action: str,
    cache_dir: object,
    cache_state: str,
    attempts: int,
) -> ModelAcquisitionError:
    """Build the single actionable error for a failed acquisition attempt."""
    return ModelAcquisitionError(
        model_name,
        action=action,
        category=categorize(exc),
        cache_dir=cache_dir,
        cache_state=cache_state,
        attempts=attempts,
        cause=cause_summary(exc),
    )


def local_load_error(
    exc: BaseException,
    *,
    model_name: str,
    cache_dir: object,
    cache_state: str,
) -> ModelAcquisitionError:
    """A cached-but-unloadable model: re-download, never blame the network.

    Used when the cache predicate said "cached" and the offline load still
    failed — that is a corrupt/incomplete local snapshot, not a connectivity
    problem, so it must not get a "check your network" remedy.
    """
    return ModelAcquisitionError(
        model_name,
        action="load",
        category=CORRUPT,
        cache_dir=cache_dir,
        cache_state=cache_state,
        attempts=1,
        cause=cause_summary(exc),
    )


def acquire_with_retry(
    func: Callable[[], T],
    *,
    model_name: str,
    action: str,
    cache_dir: object,
    cache_state: Callable[[], str],
    attempts: int = MAX_ATTEMPTS,
    base_delay: float = BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Run ``func`` with a bounded retry, raising one actionable error.

    ``func`` is the whole acquisition step (a hub download or a model load).
    Transient failures are retried up to ``attempts`` times; a missing repo or
    an auth/gated failure raises immediately. When the budget is exhausted the
    last failure is wrapped in ``ModelAcquisitionError`` naming the model, its
    cache state, and a category-specific remedy. ``cache_state`` is a callable
    because the state can change across attempts (a partial download).
    """
    budget = max(1, attempts)
    do_sleep = sleep if sleep is not None else _sleep
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - re-raised typed below
            category = categorize(exc)
            if not is_retryable(category) or attempt >= budget:
                raise acquisition_error(
                    exc,
                    model_name=model_name,
                    action=action,
                    cache_dir=cache_dir,
                    cache_state=cache_state(),
                    attempts=attempt,
                ) from exc
            delay = base_delay * (2 ** (attempt - 1))
            retry_after = _retry_after_seconds(exc)
            if retry_after is not None:
                delay = max(delay, retry_after)
            logger.debug(
                "Model acquisition attempt {}/{} for '{}' failed ({}): {}; "
                "retrying in {:.1f}s",
                attempt,
                budget,
                model_name,
                category,
                cause_summary(exc),
                delay,
            )
            do_sleep(delay)


__all__ = [
    "AUTH",
    "BASE_DELAY_SECONDS",
    "CORRUPT",
    "MAX_ATTEMPTS",
    "MISSING",
    "NETWORK",
    "RATE_LIMIT",
    "UNKNOWN",
    "acquisition_error",
    "acquire_with_retry",
    "categorize",
    "cause_summary",
    "is_retryable",
    "local_load_error",
    "redact",
]
