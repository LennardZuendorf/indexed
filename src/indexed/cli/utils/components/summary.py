"""Summary Line Component for aggregate information display.

This module provides components for displaying totals, counts, and
other summary information with consistent styling.
"""

from rich.text import Text
from .theme import get_heading_style


def create_summary(label: str, value: str) -> Text:
    """Create a summary line where the label uses accent style and the value uses heading style.

    Args:
        label: Summary label (e.g., "Total")
        value: Summary value (e.g., "39 documents, 539 chunks")

    Returns:
        Formatted Text object

    Example:
        >>> summary = create_summary("Total", "39 documents, 539 chunks")
        >>> # Renders as: "Total: 39 documents, 539 chunks"
        >>> #              ^^^^^
        >>> #           accent style
    """
    return Text(f"{label}:", style=get_heading_style()) + Text(
        f" {value}", style=get_heading_style()
    )
