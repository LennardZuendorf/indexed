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
    """
    Configure CLI root logging with Rich formatting and synchronize Loguru.
    
    Sets the module CLI log level (stored in the module's internal state), configures
    the standard library logging to use a RichHandler for formatted CLI output, and
    updates Loguru to match the chosen level.
    
    Parameters:
        level_str (Optional[str]): Log level name (e.g., "DEBUG", "INFO", "WARNING", "ERROR").
            When omitted, "WARNING" is used.
        json_mode (bool): If True, intended to enable JSON-formatted log output.
            (Used to select JSON formatting behavior when supported.)
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
    """
    Configure Loguru to emit logs to stderr at the given level with a compact, colorized format.
    
    This replaces any existing Loguru handlers with a single stderr sink that uses the format "LEVEL | message" and enables colorization. Preserves active status capture sink if present.
    
    Parameters:
        level (str): Log level name (e.g., "INFO", "DEBUG", "WARNING"); case-insensitive.
    """
    global _status_sink_id
    
    # Preserve status sink if active
    status_sink_id = _status_sink_id
    status_callback = _status_capture_callback
    
    # Remove all handlers (including status sink)
    loguru_logger.remove()
    
    # Re-add stderr handler with appropriate level
    loguru_logger.add(
        sys.stderr,
        level=level.upper(),
        format="<level>{level: <8}</level> | {message}",
        colorize=True,
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
    """
    Enable status capture that forwards INFO-level log messages to a callback.
    
    Registers a temporary Loguru sink that forwards each INFO message's text to the provided callback for use in status displays (e.g., spinners).
    
    Parameters:
        callback (Callable[[str], None]): Function invoked with the log message string for status updates.
    
    Returns:
        int: Loguru sink id that can be used to remove the sink later.
    """
    global _status_capture_enabled, _status_capture_callback, _status_sink_id

    _status_capture_enabled = True
    _status_capture_callback = callback

    def status_sink(message):
        """
        Forward INFO-level log messages received from a Loguru sink to the active status-capture callback.
        
        Parameters:
            message: The Loguru sink message object whose `record` mapping contains log metadata and the formatted `message` text. The function invokes the module's `_status_capture_callback` with `record["message"]` when the record level is "INFO" and a callback is set.
        """
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