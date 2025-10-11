"""Logging configuration for the CLI.

Configures logging levels based on CLI flags:
- Default: WARNING (clean, no noise)
- --verbose: INFO (high-level operations)
- --debug: DEBUG (everything)
"""

import logging
import os
from rich.logging import RichHandler

# Global state for status capture
_status_capture_enabled = False
_status_capture_callback = None


def setup_root_logger(level_str: str = None, json_mode: bool = False) -> None:
    """Setup root logger with appropriate level and format.
    
    Args:
        level_str: Log level as string (DEBUG, INFO, WARNING, ERROR)
        json_mode: If True, use JSON formatting for logs
    """
    if level_str:
        level = getattr(logging, level_str.upper(), logging.WARNING)
    else:
        level = logging.WARNING
    
    # Configure with Rich handler for beautiful output
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                show_time=False,
                show_path=False,
                markup=True,
                rich_tracebacks=True
            )
        ]
    )


def setup_logging(verbose: bool = False, debug: bool = False, quiet: bool = False) -> None:
    """Setup logging with appropriate level.
    
    Args:
        verbose: Show INFO level logs
        debug: Show DEBUG level logs
        quiet: Show only ERROR logs
    """
    if quiet:
        level = logging.ERROR
    elif debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    # Configure with Rich handler for beautiful output
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                show_time=False,
                show_path=False,
                markup=True,
                rich_tracebacks=True
            )
        ]
    )


def is_verbose_mode() -> bool:
    """Check if verbose mode is enabled."""
    return logging.getLogger().level <= logging.INFO


def enable_status_capture(callback) -> str:
    """Enable status capture for INFO logs.
    
    Args:
        callback: Function to call with log messages
        
    Returns:
        Sink ID for disabling later
    """
    global _status_capture_enabled, _status_capture_callback
    _status_capture_enabled = True
    _status_capture_callback = callback
    return "status_capture"


def disable_status_capture() -> None:
    """Disable status capture."""
    global _status_capture_enabled, _status_capture_callback
    _status_capture_enabled = False
    _status_capture_callback = None


__all__ = ["setup_logging", "setup_root_logger", "is_verbose_mode", "enable_status_capture", "disable_status_capture"]
