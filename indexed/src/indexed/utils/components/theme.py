"""CLI Design System Theme Constants.

This module defines all color, style, and layout constants used throughout
the CLI for consistent visual design.
"""

# ============================================================================
# Color Palette
# ============================================================================

# Primary accent color for text highlights and emphasis (not borders)
ACCENT_COLOR = "#2581C4"
ACCENT_STYLE = "bold #2581C4"

# Text hierarchy styles
TITLE_STYLE = "bold"              # Card titles, collection names
LABEL_STYLE = "bold #2581C4"      # Left-side labels (cyan and bold)
VALUE_STYLE = "not bold white"    # Right-side values (white, not bold)
SECONDARY_STYLE = "dim"           # Helper text, hints

# Status colors for feedback
ERROR_COLOR = "red"
WARNING_COLOR = "yellow"
SUCCESS_COLOR = "green"
INFO_COLOR = "blue"

# ============================================================================
# Layout Constants
# ============================================================================

# Padding inside panels/cards (vertical, horizontal)
CARD_PADDING = (0, 1)

# Label width for info rows (characters)
INFO_ROW_LABEL_WIDTH = 10

# Card widths
DETAIL_CARD_WIDTH = 60           # Single collection detail view
GRID_CARD_MIN_WIDTH = 30         # Minimum width for grid cards

# ============================================================================
# Border Styles
# ============================================================================

# Default border style for all cards (grey/dim to match Typer's help style)
CARD_BORDER_STYLE = "dim"

# ============================================================================
# Helper Functions
# ============================================================================

def get_error_style() -> str:
    """Get style string for error messages."""
    return ERROR_COLOR


def get_warning_style() -> str:
    """Get style string for warning messages."""
    return WARNING_COLOR


def get_success_style() -> str:
    """Get style string for success messages."""
    return SUCCESS_COLOR


def get_accent_style() -> str:
    """Get style string for accent/emphasis text."""
    return ACCENT_STYLE


def get_label_style() -> str:
    """Get style string for labels."""
    return LABEL_STYLE


def get_title_style() -> str:
    """Get style string for titles."""
    return TITLE_STYLE


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
        "argparse.text": ACCENT_STYLE,
    }
