"""CLI Design System Theme Constants.

This module defines all color, style, and layout constants used throughout
the CLI for consistent visual design.
"""

# ============================================================================
# Color Palette
# ============================================================================

# Primary accent color for text highlights and emphasis (not borders)
_ACCENT_COLOR = "#2581C4"
_WHITE = "white"
_ERROR_COLOR = "red"
_WARNING_COLOR = "yellow"
_SUCCESS_COLOR = "green"
_DIM_COLOR = "dim"

# Text hierarchy styles
_ACCENT_STYLE = f"bold {_ACCENT_COLOR}"
_TITLE_STYLE = f"bold underline {_ACCENT_COLOR}"  # Card titles, collection names
_HEADING_STYLE = f"bold {_WHITE}"  # Section headings and main titles
_LABEL_STYLE = f"bold {_ACCENT_COLOR}"  # Left-side labels (cyan and bold)
_VALUE_STYLE = f"not bold {_WHITE}"  # Right-side values (white, not bold)
_SECONDARY_STYLE = _DIM_COLOR  # Helper text, hints

# Status Styles
_INFO_STYLE = _DIM_COLOR
_SUCCESS_STYLE = f"bold {_SUCCESS_COLOR}"
_ERROR_STYLE = f"bold {_ERROR_COLOR}"
_WARNING_STYLE = f"bold {_WARNING_COLOR}"


# ============================================================================
# Layout Constants
# ============================================================================


# Padding inside panels/cards (vertical, horizontal)
def get_card_padding() -> tuple[int, int]:
    """Get padding for cards (vertical, horizontal)."""
    return (0, 1)


# Label width for info rows (characters)
def get_info_row_label_width() -> int:
    """Get width for info row labels in characters."""
    return 10


# Card widths
def get_detail_card_width() -> int:
    """Get width for detail cards."""
    return 60


def get_grid_card_min_width() -> int:
    """Get minimum width for grid cards."""
    return 30


# ============================================================================
# Border Styles
# ============================================================================


# Default border style for all cards (grey/dim to match Typer's help style)
def get_card_border_style() -> str:
    """Get border style for cards."""
    return "dim"


# ============================================================================
# Helper Functions
# ============================================================================


def get_error_style() -> str:
    """Get style string for error messages."""
    return _ERROR_STYLE


def get_warning_style() -> str:
    """Get style string for warning messages."""
    return _WARNING_STYLE


def get_success_style() -> str:
    """Get style string for success messages."""
    return _SUCCESS_STYLE


def get_accent_style() -> str:
    """Get style string for accent/emphasis text."""
    return _ACCENT_STYLE


def get_label_style() -> str:
    """Get style string for labels."""
    return _LABEL_STYLE


def get_default_style() -> str:
    """Get style string for default text."""
    return _WHITE


def get_secondary_style() -> str:
    """Get style string for secondary text."""
    return _SECONDARY_STYLE


def get_title_style() -> str:
    """Get style string for titles."""
    return _TITLE_STYLE


def get_dim_style() -> str:
    """Get style string for dim text."""
    return _DIM_COLOR


def get_heading_style() -> str:
    """Get style string for section headings and main titles."""
    return _HEADING_STYLE


def get_value_style() -> str:
    """Get style string for values."""
    return _VALUE_STYLE


# ============================================================================
# Rich Theme for Typer Help
# ============================================================================


def get_help_theme_styles() -> dict[str, str]:
    """Get Rich theme styles for Typer help menu customization.

    This theme ensures consistent styling with our design system:
    - Command description (docstring) is cyan and bold
    - Grey borders matching Typer's default
    - Consistent text hierarchy
    """
    return {
        # Command description/docstring - cyan and bold
        "argparse.text": _ACCENT_STYLE,
    }
