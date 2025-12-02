"""CLI logging configuration with Rich formatting.

This module extends the base logger from utils with Rich formatting
for enhanced CLI output. It provides:
- Rich-formatted console output with colors and styling
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
from rich.logging import RichHandler
import logging

# Global state for status capture (CLI-specific feature)
_status_capture_enabled = False
_status_capture_callback: Optional[Callable[[str], None]] = None
_status_sink_id: Optional[int] = None

# Track current log level for CLI
_cli_log_level = "WARNING"


def setup_root_logger(level_str: Optional[str] = None, json_mode: bool = False) -> None:
    """Setup root logger with Rich formatting for CLI.

    This configures both standard logging (with RichHandler) and Loguru
    for beautiful CLI output.

    Args:
        level_str: Log level as string (DEBUG, INFO, WARNING, ERROR)
        json_mode: If True, use JSON formatting for logs
    """
    global _cli_log_level

    effective_level = (level_str or "WARNING").upper()
    _cli_log_level = effective_level
    level = getattr(logging, effective_level, logging.WARNING)

    # Configure standard logging with Rich handler for beautiful output
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                show_time=False, show_path=False, markup=True, rich_tracebacks=True
            )
        ],
        force=True,
    )

    # Also configure loguru to match
    _configure_loguru(effective_level)


def _configure_loguru(level: str) -> None:
    """Configure loguru logger with the specified level."""
    # Remove default handler and add one with appropriate level
    loguru_logger.remove()
    loguru_logger.add(
        sys.stderr,
        level=level.upper(),
        format="<level>{level: <8}</level> | {message}",
        colorize=True,
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
    """Enable capturing INFO logs for status display.

    Adds a temporary sink that captures INFO level logs and forwards
    them to a status updater (e.g., spinner). This allows showing
    progress without cluttering the console.

    Args:
        callback: Function to call with log messages

    Returns:
        Sink ID that can be used to remove the sink later
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
