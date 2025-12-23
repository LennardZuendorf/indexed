"""Summary Line Component for aggregate information display.

This module provides components for displaying totals, counts, and
other summary information with consistent styling.

NOTE: `create_count_summary` and `create_total_summary` are DEPRECATED.
Use `create_summary` instead for all summary lines.
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


def create_count_summary(items: list[tuple[str, int]]) -> Text:
    """
    .. deprecated:: 1.0.0
       Use `create_summary` instead for all count summary lines.

    Create a summary showing multiple counts.

    Args:
        items: List of (label, count) tuples

    Returns:
        Formatted Text object with comma-separated counts

    Example:
        >>> # Instead of:
        >>> create_count_summary([
        ...     ("documents", 39),
        ...     ("chunks", 539)
        ... ])
        >>> # Use:
        >>> create_summary("Total", "39 documents, 539 chunks")
    """
    parts = [f"{count} {label}" for label, count in items]
    return Text(", ".join(parts), style=get_heading_style())


def create_total_summary(items: list[tuple[str, int]]) -> Text:
    """
    .. deprecated:: 1.0.0
       Use `create_summary('Total', ...)` instead.

    Create a "Total:" summary with counts.

    Args:
        items: List of (label, count) tuples

    Returns:
        Formatted Text object

    Example:
        >>> # Instead of:
        >>> create_total_summary([
        ...     ("documents", 39),
        ...     ("chunks", 539)
        ... ])
        >>> # Use:
        >>> create_summary("Total", "39 documents, 539 chunks")
    """
    parts = [f"{count} {label}" for label, count in items]
    return create_summary("Total", ", ".join(parts))
