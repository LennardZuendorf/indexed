"""Utilities package for indexed.

Provides reusable utilities including UI components, logging, console management,
and formatting helpers.
"""

# Re-export components for backward compatibility
from .components import *  # noqa: F401, F403

__all__ = [
    "banner",
    "config_format",
    "console",
    "logging",
    "output_mode",
    "rich_console",
    "components",
    "format_type",
]

