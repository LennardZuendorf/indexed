"""Alert components for consistent CLI messaging.

This module provides panel-based alert functions for success, error, warning,
and info messages. All alerts use simple unicode icons and colored borders
to communicate status.

Design Decisions:
- Panel-based alerts match the card-based design system
- Simple icons (✓, ✗, ⚠, ℹ) for reliable terminal rendering
- Fixed width (60 chars) to match other card widths
- Border colors communicate status (green/red/yellow/dim)
"""

from rich.panel import Panel
from rich.text import Text

from ..console import console
from .theme import (
    get_detail_card_width,
    get_card_padding,
    get_success_style,
    get_error_style,
    get_warning_style,
)

# ============================================================================
# Alert Icons (simple unicode, not emoji)
# ============================================================================

ICON_SUCCESS = "✓"
ICON_ERROR = "✗"
ICON_WARNING = "⚠"
ICON_INFO = "ℹ"


# ============================================================================
# Alert Functions
# ============================================================================


def print_success(message: str) -> None:
    """Print a success alert panel with green border.

    Args:
        message: The success message to display (icon is added automatically)

    Example:
        >>> print_success("Configuration saved successfully")
        ╭────────────────────────────────────────────────────────────╮
        │ ✓ Configuration saved successfully                         │
        ╰────────────────────────────────────────────────────────────╯
    """
    content = Text(f"{ICON_SUCCESS} {message}", style=get_success_style())
    panel = Panel(
        content,
        border_style=get_success_style(),
        padding=get_card_padding(),
        width=get_detail_card_width(),
    )
    console.print(panel)


def print_error(message: str) -> None:
    """Print an error alert panel with red border.

    Args:
        message: The error message to display (icon is added automatically)

    Example:
        >>> print_error("Failed to create collection: timeout")
        ╭────────────────────────────────────────────────────────────╮
        │ ✗ Failed to create collection: timeout                     │
        ╰────────────────────────────────────────────────────────────╯
    """
    content = Text(f"{ICON_ERROR} {message}", style=get_error_style())
    panel = Panel(
        content,
        border_style=get_error_style(),
        padding=get_card_padding(),
        width=get_detail_card_width(),
    )
    console.print(panel)


def print_warning(message: str) -> None:
    """Print a warning alert panel with yellow border.

    Args:
        message: The warning message to display (icon is added automatically)

    Example:
        >>> print_warning("This will remove the key from config")
        ╭────────────────────────────────────────────────────────────╮
        │ ⚠ This will remove the key from config                     │
        ╰────────────────────────────────────────────────────────────╯
    """
    content = Text(f"{ICON_WARNING} {message}", style=get_warning_style())
    panel = Panel(
        content,
        border_style=get_warning_style(),
        padding=get_card_padding(),
        width=get_detail_card_width(),
    )
    console.print(panel)


def print_info(message: str) -> None:
    """Print an info alert panel with dim border.

    Args:
        message: The info message to display (icon is added automatically)

    Example:
        >>> print_info("Key not found in workspace config")
        ╭────────────────────────────────────────────────────────────╮
        │ ℹ Key not found in workspace config                        │
        ╰────────────────────────────────────────────────────────────╯
    """
    content = Text(f"{ICON_INFO} {message}", style="dim")
    panel = Panel(
        content,
        border_style="dim",
        padding=get_card_padding(),
        width=get_detail_card_width(),
    )
    console.print(panel)


__all__ = [
    "print_success",
    "print_error",
    "print_warning",
    "print_info",
    "ICON_SUCCESS",
    "ICON_ERROR",
    "ICON_WARNING",
    "ICON_INFO",
]

