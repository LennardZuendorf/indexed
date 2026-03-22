"""CLI logging configuration with Rich formatting.

This module extends the base logger from utils with Rich formatting
for enhanced CLI output. It provides:
- Loguru sink that routes through the shared Console instance
- Status capture for spinner/progress integration
- CLI-specific logging conveniences

For non-CLI usage (library, server), use utils.logger directly.

Configures logging levels based on CLI flags:
- Default: WARNING (clean, no noise)
- --verbose: INFO (high-level operations)
- --debug: DEBUG (everything)
"""

import sys
from typing import Callable, Optional

from loguru import logger as loguru_logger
import logging

from .console import console

# Global state for status capture (CLI-specific feature)
_status_capture_enabled = False
_status_capture_callback: Optional[Callable[[str], None]] = None
_status_sink_id: Optional[int] = None

# Track current log level for CLI
_cli_log_level = "WARNING"


def _loguru_console_sink(message) -> None:
    """Loguru sink that routes output through the shared Rich Console.

    This ensures all log output goes through the single Console instance,
    preventing conflicts with Rich Live/Progress/Status displays.
    """
    record = message.record
    level = record["level"].name

    # Map Loguru levels to Rich styles
    style_map = {
        "TRACE": "dim",
        "DEBUG": "dim",
        "INFO": "dim",
        "SUCCESS": "dim green",
        "WARNING": "yellow",
        "ERROR": "bold red",
        "CRITICAL": "bold red reverse",
    }
    style = style_map.get(level, "dim")

    # Format: "LEVEL    | message" with dim timestamp in verbose mode
    text = f"[{style}]{level: <8} | {record['message']}[/{style}]"
    console.print(text, highlight=False)


def setup_root_logger(level_str: Optional[str] = None, json_mode: bool = False) -> None:
    """Configure CLI root logging with Rich formatting and synchronize Loguru.

    Routes all Loguru output through the shared Console instance to prevent
    output conflicts with Rich Live/Progress/Status displays.

    Parameters:
        level_str: Log level name (e.g., "DEBUG", "INFO", "WARNING", "ERROR").
            When omitted, "WARNING" is used.
        json_mode: If True, use plain stderr sink instead of Rich console sink
            for structured/JSON log output.
    """
    global _cli_log_level

    effective_level = (level_str or "WARNING").upper()
    _cli_log_level = effective_level
    level = getattr(logging, effective_level, logging.WARNING)

    # Suppress standard library logging — we use Loguru exclusively
    logging.basicConfig(level=level, format="%(message)s", force=True)
    logging.getLogger().handlers = []
    logging.getLogger().setLevel(level)

    # Configure Loguru to route through shared console
    _configure_loguru(effective_level, json_mode)


def _configure_loguru(level: str, json_mode: bool = False) -> None:
    """Configure Loguru to route through the shared Console instance.

    Parameters:
        level: Log level name (e.g., "INFO", "DEBUG", "WARNING").
        json_mode: If True, use plain stderr sink for JSON output.
    """
    global _status_sink_id

    # Preserve status sink if active
    status_sink_id = _status_sink_id
    status_callback = _status_capture_callback

    # Remove all handlers (including status sink)
    loguru_logger.remove()

    if json_mode:
        # JSON mode: plain stderr, no Rich formatting
        loguru_logger.add(
            sys.stderr,
            level=level.upper(),
            format="<level>{level: <8}</level> | {message}",
            colorize=True,
        )
    else:
        # Normal mode: route through shared Console to avoid output conflicts
        loguru_logger.add(
            _loguru_console_sink,
            level=level.upper(),
            format="{message}",
            colorize=False,
        )

    # Re-register status sink if it was active
    if status_sink_id is not None and status_callback is not None:

        def status_sink(message):
            record = message.record
            if record["level"].name == "INFO" and status_callback:
                status_callback(record["message"])

        _status_sink_id = loguru_logger.add(
            status_sink,
            level="INFO",
            format="{message}",
            filter=lambda record: record["level"].name == "INFO",
        )


def setup_logging(
    verbose: bool = False, debug: bool = False, quiet: bool = False
) -> None:
    """Setup logging with appropriate level based on CLI flags.

    This is a convenience function for CLI applications that use
    boolean flags for verbosity control.

    Args:
        verbose: Show INFO level logs
        debug: Show DEBUG level logs
        quiet: Show only ERROR logs
    """
    if quiet:
        level_str = "ERROR"
    elif debug:
        level_str = "DEBUG"
    elif verbose:
        level_str = "INFO"
    else:
        level_str = "WARNING"

    setup_root_logger(level_str)


def is_verbose_mode() -> bool:
    """Check if verbose mode is enabled.

    Returns:
        True if log level is INFO or DEBUG, False otherwise
    """
    return _cli_log_level in ("INFO", "DEBUG")


def enable_status_capture(callback: Callable[[str], None]) -> int:
    """Enable status capture that forwards INFO-level log messages to a callback.

    Registers a temporary Loguru sink that forwards each INFO message's text
    to the provided callback for use in status displays (e.g., spinners).

    Parameters:
        callback: Function invoked with the log message string for status updates.

    Returns:
        Loguru sink id that can be used to remove the sink later.
    """
    global _status_capture_enabled, _status_capture_callback, _status_sink_id

    _status_capture_enabled = True
    _status_capture_callback = callback

    def status_sink(message):
        record = message.record
        if record["level"].name == "INFO" and _status_capture_callback:
            _status_capture_callback(record["message"])

    _status_sink_id = loguru_logger.add(
        status_sink,
        level="INFO",
        format="{message}",
        filter=lambda record: record["level"].name == "INFO",
    )

    return _status_sink_id


def disable_status_capture() -> None:
    """Disable INFO log capture for status display."""
    global _status_capture_enabled, _status_capture_callback, _status_sink_id

    if _status_sink_id is not None:
        loguru_logger.remove(_status_sink_id)
        _status_sink_id = None

    _status_capture_enabled = False
    _status_capture_callback = None


__all__ = [
    "setup_logging",
    "setup_root_logger",
    "is_verbose_mode",
    "enable_status_capture",
    "disable_status_capture",
]
