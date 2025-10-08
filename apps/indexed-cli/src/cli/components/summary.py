"""Summary Line Component for aggregate information display.

This module provides components for displaying totals, counts, and
other summary information with consistent styling.
"""

from rich.text import Text
from .theme import ACCENT_STYLE


def create_summary(label: str, value: str) -> Text:
    """Create a summary line with cyan accent.
    
    Args:
        label: Summary label (e.g., "Total")
        value: Summary value (e.g., "39 documents, 539 chunks")
    
    Returns:
        Formatted Text object
        
    Example:
        >>> summary = create_summary("Total", "39 documents, 539 chunks")
        >>> # Renders as: "Total: 39 documents, 539 chunks"
        >>> #              ^^^^^
        >>> #              cyan bold
    """
    return Text(f"{label}:", style=ACCENT_STYLE) + Text(f" {value}")


def create_count_summary(items: list[tuple[str, int]]) -> Text:
    """Create a summary showing multiple counts.
    
    Args:
        items: List of (label, count) tuples
    
    Returns:
        Formatted Text object with comma-separated counts
        
    Example:
        >>> summary = create_count_summary([
        ...     ("documents", 39),
        ...     ("chunks", 539)
        ... ])
        >>> # Renders as: "39 documents, 539 chunks"
    """
    parts = [f"{count} {label}" for label, count in items]
    return Text(", ".join(parts))


def create_total_summary(items: list[tuple[str, int]]) -> Text:
    """Create a "Total:" summary with counts.
    
    Convenience wrapper combining create_summary and create_count_summary.
    
    Args:
        items: List of (label, count) tuples
    
    Returns:
        Formatted Text object
        
    Example:
        >>> summary = create_total_summary([
        ...     ("documents", 39),
        ...     ("chunks", 539)
        ... ])
        >>> # Renders as: "Total: 39 documents, 539 chunks"
    """
    count_text = create_count_summary(items)
    return Text("Total:", style=ACCENT_STYLE) + Text(f" {count_text}")
