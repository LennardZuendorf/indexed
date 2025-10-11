"""Card Components for consistent panel display.

This module provides reusable card (panel) components for displaying
information in bordered containers with consistent styling.
"""

from typing import Optional
from rich.panel import Panel
from rich.console import Group

from .theme import (
    CARD_BORDER_STYLE,
    CARD_PADDING,
    TITLE_STYLE,
    DETAIL_CARD_WIDTH,
)
from .info_row import create_info_rows


def create_info_card(
    title: str,
    rows: list[tuple[str, str]],
    width: Optional[int] = None,
    subtitle: Optional[str] = None,
) -> Panel:
    """Create a card panel containing info rows.
    
    Args:
        title: Card title (will be bolded)
        rows: List of (label, value) tuples for info rows
        width: Optional fixed width (default: auto)
        subtitle: Optional subtitle text in parentheses after title
    
    Returns:
        Panel with formatted content
        
    Example:
        >>> card = create_info_card(
        ...     title="files",
        ...     rows=[("Docs", "13"), ("Chunks", "174")],
        ...     subtitle="localFiles"
        ... )
    """
    # Create content from info rows
    content = Group(*create_info_rows(rows))
    
    # Build title with optional subtitle
    if subtitle:
        title_text = f"[{TITLE_STYLE}]{title}[/{TITLE_STYLE}] [dim]({subtitle})[/dim]"
    else:
        title_text = f"[{TITLE_STYLE}]{title}[/{TITLE_STYLE}]"
    
    return Panel(
        content,
        title=title_text,
        title_align="left",
        border_style=CARD_BORDER_STYLE,
        padding=CARD_PADDING,
        width=width,
    )


def create_detail_card(
    title: str,
    rows: list[tuple[str, str]],
    subtitle: Optional[str] = None,
) -> Panel:
    """Create a fixed-width detail card for single item display.
    
    This is a convenience wrapper around create_info_card() with
    the standard detail view width.
    
    Args:
        title: Card title
        rows: List of (label, value) tuples
        subtitle: Optional subtitle
    
    Returns:
        Panel with fixed width
    """
    return create_info_card(
        title=title,
        rows=rows,
        width=DETAIL_CARD_WIDTH,
        subtitle=subtitle,
    )


def create_grid_cards(
    items: list[dict],
    title_key: str = "title",
    rows_key: str = "rows",
    subtitle_key: Optional[str] = None,
) -> list[Panel]:
    """Create multiple cards for grid layout from structured data.
    
    Args:
        items: List of dicts, each containing card data
        title_key: Key for title in each dict
        rows_key: Key for rows list in each dict
        subtitle_key: Optional key for subtitle in each dict
    
    Returns:
        List of Panel objects ready for grid display
        
    Example:
        >>> items = [
        ...     {
        ...         "title": "files",
        ...         "subtitle": "localFiles",
        ...         "rows": [("Docs", "13"), ("Chunks", "174")]
        ...     },
        ...     {
        ...         "title": "memory",
        ...         "rows": [("Docs", "13"), ("Chunks", "174")]
        ...     }
        ... ]
        >>> cards = create_grid_cards(items, subtitle_key="subtitle")
    """
    cards = []
    for item in items:
        subtitle = item.get(subtitle_key) if subtitle_key else None
        card = create_info_card(
            title=item[title_key],
            rows=item[rows_key],
            subtitle=subtitle,
        )
        cards.append(card)
    return cards
