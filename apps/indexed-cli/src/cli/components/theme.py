"""CLI Design System Theme Constants.

This module defines all color, style, and layout constants used throughout
the CLI for consistent visual design.
"""

# ============================================================================
# Color Palette
# ============================================================================

# Primary accent color for borders, highlights, and emphasis
ACCENT_COLOR = "cyan"
ACCENT_STYLE = "bold cyan"

# Text hierarchy styles
TITLE_STYLE = "bold"              # Card titles, collection names
LABEL_STYLE = "dim"               # Left-side labels (grey)
VALUE_STYLE = ""                  # Right-side values (white/default)
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

# Default border style for all cards
CARD_BORDER_STYLE = ACCENT_COLOR

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
