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
    # Message is a stub-only construct (loguru's runtime __init__ only
    # exports `logger`, per its __all__) — safe to import here since this
    # file has `from __future__ import annotations`, so the annotation is
    # never evaluated at runtime.
    from loguru import Message
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
    # The Hub's one-time notice ("Warning: You are sending unauthenticated
    # requests ...", delivered via the X-HF-Warning header) is a WARNING, so the
    # floor has to be WARNING for it to reach the user at all; its own handler
    # is stripped by ``_apply_policy`` so it renders exactly once, through
    # Loguru. File-download retries log at INFO (below this floor). --debug
    # lowers it back to DEBUG for the full timeline.
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
_DEBUG = False

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
            level, _drop_redundant_level_prefix(record.getMessage(), record.levelname)
        )


def _drop_redundant_level_prefix(message: str, level_name: str) -> str:
    """Strip a leading ``"<LEVEL>: "`` the library already baked into ``message``.

    The Hub's notice arrives as ``"Warning: You are sending ..."`` — the server
    prefixes the header value itself. The console sink renders the level, so
    keeping it would print ``WARNING  | Warning: ...``. Only the record's OWN
    level is stripped, so text that merely starts with a level word (an ERROR
    whose message begins with "Warning:") is left untouched.
    """
    prefix = f"{level_name}:"
    if message[: len(prefix)].lower() == prefix.lower():
        return message[len(prefix) :].lstrip()
    return message


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
) -> Callable[[Message], None]:
    """Build a Loguru sink callable.

    When ``rich_console`` is provided, output goes through it and theme styles
    wrap the level + message. Otherwise output goes to stderr as plain text.
    """

    def sink(message: Message) -> None:
        record = message.record
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
            # `line` is log content (message text, may embed user input like
            # a search query or a repr) — never markup-parsed. A raw
            # f"[{style}]{line}[/{style}]" string would have bracket
            # characters in `line` parsed as style tags (silently dropping
            # them, or raising MarkupError that loguru's catch=True would
            # then swallow in place of the real message). `Text` renders the
            # content literally while still applying `style`.
            from rich.text import Text

            rich_console.print(Text(line, style=style), highlight=False)
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
                # Same literal-rendering rationale as the message above —
                # a traceback commonly contains bracketed reprs (e.g.
                # `list[int]`, `dict_keys([...])`).
                from rich.text import Text

                rich_console.print(Text(tb_text, style=style), highlight=False)
            else:
                print(tb_text, file=sys.stderr)

    return sink


def _make_status_sink() -> Callable[[Message], None]:
    """Status sink: filtered records fan out to all subscribers."""

    def sink(message: Message) -> None:
        record = message.record
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


def _apply_policy(name: str) -> None:
    """Attach the NullHandler defense and the effective level for one library."""
    lib_logger = logging.getLogger(name)
    # Drop whatever the library attached to itself: a plain StreamHandler writes
    # unformatted lines straight to stderr, bypassing verbosity gating entirely.
    for handler in list(lib_logger.handlers):
        if not isinstance(handler, logging.NullHandler):
            lib_logger.removeHandler(handler)
    if not any(isinstance(h, logging.NullHandler) for h in lib_logger.handlers):
        lib_logger.addHandler(logging.NullHandler())
    lib_logger.setLevel(
        logging.DEBUG if _DEBUG else getattr(logging, THIRD_PARTY_LOGGERS[name])
    )
    # Keep propagate=True so InterceptHandler at root still receives it.
    lib_logger.propagate = True


def enforce_third_party_policy(*names: str) -> None:
    """Re-assert ``THIRD_PARTY_LOGGERS`` after a library reconfigures itself.

    Some dependencies configure their own logger at import time:
    ``huggingface_hub.utils.logging`` attaches a bare ``StreamHandler`` and sets
    its root logger to WARNING. Every ML import in indexed is lazy, so that runs
    *after* ``bootstrap_logging`` and silently undoes both the policy level and
    the single-sink guarantee — the library's handler prints the record raw AND
    the record still propagates into Loguru (the #211 duplicate notice).

    Call this immediately after such an import; that import is the only moment
    the clobber is observable. Idempotent, and a no-op until
    ``bootstrap_logging`` has run, so a library import in a bare test/library
    context never installs the CLI's sinks.
    """
    if not _LOGGING_CONFIGURED:
        return
    for name in names:
        if name in THIRD_PARTY_LOGGERS:
            _apply_policy(name)


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
        rich_console: Rich Console for the console sink. The caller picks the
            stream: the CLI passes its stderr-backed ``log_console`` so records
            never enter a machine-readable stdout. When None, the console sink
            writes plain text to stderr.
        theme_styles: Mapping of Loguru level name → Rich style markup. Used
            only when ``rich_console`` is also provided. The CLI builds this
            from ``apps/indexed/.../components/theme.py`` accessors.
        log_dir: Directory for the rotating debug-mode file sink. Created if
            missing. Ignored unless ``debug=True``.
        json_mode: Reserved. Currently a no-op — see plan U3 deferred question.
    """
    global _LOGGING_CONFIGURED, _CURRENT_LOG_LEVEL, _QUIET, _DEBUG

    effective_level = (level or "WARNING").upper()
    _CURRENT_LOG_LEVEL = effective_level
    _QUIET = quiet
    _DEBUG = debug
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

    # 4. Per-library policy: NullHandler defense + level. Re-runnable — a
    # library that configures itself on a lazy import is repaired by
    # enforce_third_party_policy() at that import site.
    for name in THIRD_PARTY_LOGGERS:
        _apply_policy(name)

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


def setup_root_logger(level_str: Optional[str] = None, json_mode: bool = False) -> None:
    """Deprecated shim — calls ``bootstrap_logging`` for old callers.

    Kept to avoid breaking imports during the migration. New code should call
    ``bootstrap_logging`` directly with the full verbosity matrix.

    When ``level_str`` is ``None`` and logging has already been configured
    (normally by the app callback, which resolves ``--verbose``/
    ``--log-level``/``INDEXED_LOG_LEVEL`` once and calls ``bootstrap_logging``
    directly), this is a no-op: it must NOT reset the level back to WARNING
    and clobber the callback's resolved level — that silently defeated every
    knowledge command's verbosity flags (foundation/6c bug E3). Falls back to
    WARNING only when nothing has configured logging yet in this process.
    """
    if level_str is None:
        if _LOGGING_CONFIGURED:
            return
        level_str = "WARNING"
    bootstrap_logging(level=level_str, json_mode=json_mode)


__all__ = [
    "THIRD_PARTY_LOGGERS",
    "InterceptHandler",
    "bootstrap_logging",
    "emit_status",
    "enforce_third_party_policy",
    "subscribe_status",
    "unsubscribe_status",
    "is_verbose_mode",
    "get_current_log_level",
    "setup_root_logger",  # shim
]
