"""Info Row Component for consistent label-value display.

This module provides a reusable component for displaying label-value pairs
with consistent formatting and alignment across all CLI commands.
"""

from rich.text import Text
from .theme import get_info_row_label_width, get_label_style, get_value_style


def create_info_row(label: str, value: str) -> Text:
    """Create a consistently formatted info row with grey label and white value.

    This is the foundation for all label-value displays in the CLI. It ensures
    consistent alignment, spacing, and styling across all commands.

    Args:
        label: The label text (will be styled dim/grey)
        value: The value text (will be styled normal/white)

    Returns:
        Text object with formatted label and value

    Example:
        >>> row = create_info_row("Docs", "13")
        >>> # Renders as: "Docs      13"
        >>> #              ^^^^      ^^
        >>> #              grey      white
    """
    # Pad label to consistent width for alignment
    padded_label = f"{label:<{get_info_row_label_width()}}"
    return Text(padded_label, style=get_label_style()) + Text(
        value, style=get_value_style()
    )


def create_info_rows(data: list[tuple[str, str]]) -> list[Text]:
    """Create multiple info rows from a list of (label, value) tuples.

    Args:
        data: List of (label, value) tuples

    Returns:
        List of formatted Text objects

    Example:
        >>> rows = create_info_rows([
        ...     ("Docs", "13"),
        ...     ("Chunks", "174"),
        ... ])
    """
    return [create_info_row(label, value) for label, value in data]
