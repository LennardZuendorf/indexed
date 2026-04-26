"""Single-sink Loguru architecture for the indexed CLI and library code.

All log records — both Loguru and stdlib `logging` — flow through one Loguru
configuration. The bootstrap is idempotent and called at CLI entry; verbosity
is set once per session.

Design (see docs/plans/2026-04-25-001-refactor-cli-logging-pipeline-plan.md):

- ``InterceptHandler`` (loguru recipe) on root stdlib logger forwards every
  ``logging`` record into Loguru with original level/file/line preserved.
- ``logging.lastResort = None`` kills the silent stderr fallback.
- Per noisy third-party library: ``NullHandler`` attached + level set per
  ``THIRD_PARTY_LOGGERS`` policy. ``NullHandler`` ensures the stdlib record
  walk finds a handler so ``lastResort`` is never reached even if a noisy lib
  appears that we forgot to add to the policy.
- Three sinks, all Loguru:
    * console — verbosity-gated; renders via Rich when ``rich_console`` is
      injected by the CLI, plain text otherwise.
    * status — filtered by ``record["extra"]["status"]``; fans out to
      subscribers via ``subscribe_status`` / ``unsubscribe_status``. Disabled
      when ``quiet=True``.
    * file — only when ``debug=True`` and ``log_dir`` is provided. Daily
      rotation, 7-day retention.
- No hard-coded colors. Theme styles flow in via the ``theme_styles`` dict so
  utils stays Rich-optional and theme-agnostic.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from loguru import logger

if TYPE_CHECKING:
    from rich.console import Console


# ---------------------------------------------------------------------------
# Public policy table
# ---------------------------------------------------------------------------

THIRD_PARTY_LOGGERS: dict[str, str] = {
    # docling is wrapped by indexed-parsing — our wrapper already logs failures
    # at the right level. Docling's own ERRORs (e.g. format-mismatch on files
    # the wrapper deliberately routes through) are pure noise at default.
    "docling": "CRITICAL",
    "docling_core": "CRITICAL",
    # transformers / sentence_transformers ERRORs are informative (model load
    # fallbacks, missing weights). Keep ERROR-and-above visible.
    "transformers": "ERROR",
    "sentence_transformers": "WARNING",
    "urllib3": "WARNING",
    "huggingface_hub": "WARNING",
    "filelock": "WARNING",
    # Python's `warnings` module is bridged into logging via
    # `logging.captureWarnings(True)` in bootstrap_logging — records arrive
    # under the `py.warnings` logger. Treat them like any other noisy lib.
    "py.warnings": "ERROR",
}
"""Default level per noisy third-party logger.

In ``--debug`` (``debug=True``), every entry is lowered to ``DEBUG`` so the
user can see what these libraries are doing. Otherwise the level here is the
floor — records below this never enter Loguru.

Add a new entry when a noisy dependency surfaces. Removing an entry is fine
too; the ``InterceptHandler`` + dead ``lastResort`` defense still prevents
raw stderr leaks.
"""


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_LOGGING_CONFIGURED = False
_CURRENT_LOG_LEVEL = "WARNING"
_QUIET = False

# Status subscribers — opaque tokens map to callbacks
_status_subscribers: dict[int, Callable[[str], None]] = {}
_next_status_token = 0


# ---------------------------------------------------------------------------
# Stdlib → Loguru bridge
# ---------------------------------------------------------------------------


class InterceptHandler(logging.Handler):
    """Forward stdlib logging records into Loguru, preserving level & origin."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller depth so loguru's {name}/{line} reflect the original site.
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# ---------------------------------------------------------------------------
# Sink factories
# ---------------------------------------------------------------------------


_DEFAULT_THEME_STYLES: dict[str, str] = {
    "TRACE": "dim",
    "DEBUG": "dim",
    "INFO": "",
    "SUCCESS": "",
    "WARNING": "",
    "ERROR": "",
    "CRITICAL": "",
}


def _make_console_sink(
    rich_console: Optional["Console"],
    theme_styles: dict[str, str],
    show_details: bool,
) -> Callable[[object], None]:
    """Build a Loguru sink callable.

    When ``rich_console`` is provided, output goes through it and theme styles
    wrap the level + message. Otherwise output goes to stderr as plain text.
    """

    def sink(message: object) -> None:
        record = message.record  # type: ignore[attr-defined]
        # Skip status records — they belong to the status sink.
        if record["extra"].get("status"):
            return

        level_name = record["level"].name
        msg = record["message"]
        style = theme_styles.get(level_name, "")

        if show_details:
            origin = f"({record['name']}:{record['line']})"
            line = f"{level_name:<8} | {origin} {msg}"
        else:
            line = f"{level_name:<8} | {msg}"

        if rich_console is not None:
            if style:
                rich_console.print(f"[{style}]{line}[/{style}]", highlight=False)
            else:
                rich_console.print(line, highlight=False)
        else:
            print(line, file=sys.stderr)

        # Render exception traceback if attached.
        exc = record["exception"]
        if exc is not None:
            import traceback as tb_mod

            tb_text = "".join(
                tb_mod.format_exception(exc.type, exc.value, exc.traceback)
            ).rstrip()
            if rich_console is not None:
                if style:
                    rich_console.print(f"[{style}]{tb_text}[/{style}]", highlight=False)
                else:
                    rich_console.print(tb_text, highlight=False)
            else:
                print(tb_text, file=sys.stderr)

    return sink


def _make_status_sink() -> Callable[[object], None]:
    """Status sink: filtered records fan out to all subscribers."""

    def sink(message: object) -> None:
        record = message.record  # type: ignore[attr-defined]
        if not record["extra"].get("status"):
            return
        msg = record["message"]
        for cb in list(_status_subscribers.values()):
            try:
                cb(msg)
            except Exception:  # noqa: BLE001
                # A misbehaving subscriber must not break logging.
                continue

    return sink


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap_logging(
    level: str = "WARNING",
    *,
    debug: bool = False,
    quiet: bool = False,
    rich_console: Optional["Console"] = None,
    theme_styles: Optional[dict[str, str]] = None,
    log_dir: Optional[Path] = None,
    json_mode: bool = False,
) -> None:
    """Configure the entire logging stack. Idempotent — safe to call repeatedly.

    Parameters mirror the Strict verbosity matrix from the plan:

    | Flag        | level     | quiet | debug |
    |-------------|-----------|-------|-------|
    | _(default)_ | WARNING   | False | False |
    | --verbose   | INFO      | False | False |
    | --debug     | DEBUG     | False | True  |
    | --quiet     | ERROR     | True  | False |

    Args:
        level: Effective console level (already resolved by the caller).
        debug: When True, third-party loggers drop to DEBUG and the file sink
            is enabled if ``log_dir`` is provided.
        quiet: When True, the status sink is not registered (spinner stays
            silent) and the console sink emits only ERROR+.
        rich_console: Shared Rich Console instance. When None, the console
            sink writes plain text to stderr.
        theme_styles: Mapping of Loguru level name → Rich style markup. Used
            only when ``rich_console`` is also provided. The CLI builds this
            from ``apps/indexed/.../components/theme.py`` accessors.
        log_dir: Directory for the rotating debug-mode file sink. Created if
            missing. Ignored unless ``debug=True``.
        json_mode: Reserved. Currently a no-op — see plan U3 deferred question.
    """
    global _LOGGING_CONFIGURED, _CURRENT_LOG_LEVEL, _QUIET

    effective_level = (level or "WARNING").upper()
    _CURRENT_LOG_LEVEL = effective_level
    _QUIET = quiet
    styles = theme_styles if theme_styles is not None else _DEFAULT_THEME_STYLES

    # 1. Wipe loguru handlers — we own them all.
    logger.remove()

    # 2. Stdlib root: clear handlers, capture everything via InterceptHandler.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG)  # capture all; gate at sinks
    root.addHandler(InterceptHandler())

    # 3. Kill the lastResort stderr fallback.
    logging.lastResort = None

    # 3b. Route `warnings.warn(...)` through stdlib logging so it goes
    # through the InterceptHandler instead of leaking to stderr directly.
    # Records arrive under the `py.warnings` logger (gated in step 4).
    logging.captureWarnings(True)

    # 4. Per-library policy: NullHandler defense + level.
    for name, default_level in THIRD_PARTY_LOGGERS.items():
        lib_logger = logging.getLogger(name)
        # Set effective level: DEBUG when --debug, else policy default.
        target_level = "DEBUG" if debug else default_level
        lib_logger.setLevel(getattr(logging, target_level))
        # Attach NullHandler if not already present (idempotent).
        if not any(isinstance(h, logging.NullHandler) for h in lib_logger.handlers):
            lib_logger.addHandler(logging.NullHandler())
        # Keep propagate=True so InterceptHandler at root still receives it.
        lib_logger.propagate = True

    # 5. Console sink (always; level-gated).
    show_details = effective_level in ("DEBUG", "INFO")
    logger.add(
        _make_console_sink(rich_console, styles, show_details),
        level=effective_level,
        format="{message}",  # sink ignores; built manually for theme control
    )

    # 6. Status sink (skipped when quiet).
    if not quiet:
        logger.add(
            _make_status_sink(),
            level="INFO",  # status messages emitted at INFO with extra
            format="{message}",
            filter=lambda r: bool(r["extra"].get("status")),
        )

    # 7. File sink (only --debug + log_dir).
    if debug and log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "indexed-{time:YYYY-MM-DD}.log"
        logger.add(
            str(log_path),
            level="DEBUG",
            rotation="00:00",  # daily
            retention="7 days",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} | {message}",
            enqueue=False,
        )

    _LOGGING_CONFIGURED = True


# ---------------------------------------------------------------------------
# Status API
# ---------------------------------------------------------------------------


def emit_status(message: str) -> None:
    """Emit a progress status message.

    Status messages are routed to subscribers (e.g. spinner UI) via the status
    sink, independent of console verbosity. They are skipped under
    ``--quiet``.
    """
    logger.bind(status=True).info(message)


def subscribe_status(callback: Callable[[str], None]) -> int:
    """Register a callback to receive status messages. Returns an opaque token."""
    global _next_status_token
    token = _next_status_token
    _next_status_token += 1
    _status_subscribers[token] = callback
    return token


def unsubscribe_status(token: int) -> None:
    """Remove a previously registered status subscriber. Idempotent."""
    _status_subscribers.pop(token, None)


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------


def is_verbose_mode() -> bool:
    """Return True when the effective console level is INFO or DEBUG."""
    return _CURRENT_LOG_LEVEL in ("INFO", "DEBUG")


def get_current_log_level() -> str:
    """Return the current effective console log level."""
    return _CURRENT_LOG_LEVEL


# ---------------------------------------------------------------------------
# Backwards-compatible shim
# ---------------------------------------------------------------------------


def setup_root_logger(
    level_str: Optional[str] = None, json_mode: bool = False
) -> None:
    """Deprecated shim — calls ``bootstrap_logging`` for old callers.

    Kept to avoid breaking imports during the migration. New code should call
    ``bootstrap_logging`` directly with the full verbosity matrix.
    """
    bootstrap_logging(level=level_str or "WARNING", json_mode=json_mode)


__all__ = [
    "THIRD_PARTY_LOGGERS",
    "InterceptHandler",
    "bootstrap_logging",
    "emit_status",
    "subscribe_status",
    "unsubscribe_status",
    "is_verbose_mode",
    "get_current_log_level",
    "setup_root_logger",  # shim
]
