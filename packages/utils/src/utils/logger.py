"""Base logging configuration using Loguru.

This module provides a lightweight logging setup using pure Loguru without
Rich dependencies. For CLI applications that need Rich formatting, use the
CLI logging module which extends this base configuration.

Configures logging levels:
- Default: WARNING (clean, no noise)
- Verbose: INFO (high-level operations)
- Debug: DEBUG (everything)
"""

import sys
from typing import Optional

from loguru import logger

_LOGGING_CONFIGURED = False
_CURRENT_LOG_LEVEL = "WARNING"


def setup_root_logger(level_str: Optional[str] = None, json_mode: bool = False) -> None:
    """Setup Loguru with simple stderr output.

    This is the base logger configuration without Rich formatting.
    For Rich-enhanced logging in CLI applications, use the CLI logging module.

    Args:
        level_str: Log level (DEBUG, INFO, WARNING, ERROR)
        json_mode: Output logs as JSON for machine parsing
    """
    global _LOGGING_CONFIGURED, _CURRENT_LOG_LEVEL

    if _LOGGING_CONFIGURED:
        # Allow reconfiguration by removing all sinks
        logger.remove()

    effective_level = (level_str or "WARNING").upper()
    _CURRENT_LOG_LEVEL = effective_level

    # In verbose/debug mode: show source path and time
    # In default mode: minimal output
    show_details = effective_level in ("DEBUG", "INFO")

    if json_mode:
        # JSON format for production/machine parsing
        logger.add(
            sys.stderr,
            level=effective_level,
            format="{message}",
            serialize=True,
        )
    elif show_details:
        # Verbose mode: show time, level, source, message
        logger.add(
            sys.stderr,
            level=effective_level,
            format="<dim>{time:HH:mm:ss}</dim> <level>{level: <8}</level> <dim>({name}:{line})</dim> {message}",
            colorize=True,
        )
    else:
        # Default mode: just level and message
        logger.add(
            sys.stderr,
            level=effective_level,
            format="<level>{level}</level>: {message}",
            colorize=True,
        )

    _LOGGING_CONFIGURED = True


def is_verbose_mode() -> bool:
    """Check if verbose or debug mode is enabled.

    Returns:
        True if log level is INFO or DEBUG, False otherwise
    """
    return _CURRENT_LOG_LEVEL in ("INFO", "DEBUG")


def get_current_log_level() -> str:
    """Get the current log level.

    Returns:
        Current log level as string (DEBUG, INFO, WARNING, ERROR)
    """
    return _CURRENT_LOG_LEVEL


__all__ = [
    "setup_root_logger",
    "is_verbose_mode",
    "get_current_log_level",
]
