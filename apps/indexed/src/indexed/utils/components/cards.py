# Start of Selection
"""Card Components for consistent panel display.

This module provides reusable card (panel) components for displaying
information in bordered containers with consistent styling.
"""

from typing import Optional, Sequence
from rich.panel import Panel
from rich.console import Group
from rich.table import Table
from rich.text import Text

from .theme import (
    get_card_border_style,
    get_card_padding,
    get_detail_card_width,
    get_value_style,
    get_label_style,
)


def create_info_rows_with_spacing(rows: Sequence[tuple[str, "str | Text"]]) -> list:
    """
    Create info rows with proper spacing between the label and the value.
    Uses a Rich Table with two columns for neat alignment.

    ``value`` is always rendered literally (never parsed as Rich markup)
    unless the caller passes an already-built ``rich.text.Text`` — e.g.
    ``Text.from_markup(...)`` for deliberately styled content such as a
    color-coded delta. Plain ``str`` values may be user/content-derived
    (search excerpts, document ids, config values) and must never be
    interpreted as markup: a value containing ``[/bold]`` or ``arr[i]``
    would otherwise crash ``Text.from_markup`` or have the bracketed
    portion silently swallowed (foundation/6c bug E2). Callers that need
    styled output must build a ``Text`` themselves — do not rely on this
    function to guess intent from bracket characters.
    """
    table = Table.grid(expand=True, padding=(0, 1))
    # Set appropriate alignment and style for columns
    table.add_column(
        justify="left", style=get_label_style(), ratio=1
    )  # Use label_style for left column
    table.add_column(justify="right", ratio=2)
    value_style = get_value_style()
    for label, value in rows:
        label_text = str(label)
        if isinstance(value, Text):
            # Caller deliberately built styled markup — use as-is.
            value_text = value
        else:
            # Plain/untrusted content: literal text, never markup-parsed.
            value_text = Text(str(value), style=value_style)
        table.add_row(label_text, value_text)
    return [table]


def create_info_card(
    title: str,
    rows: Sequence[tuple[str, "str | Text"]],
    width: Optional[int] = None,
    subtitle: Optional[str] = None,
) -> Panel:
    """Create a card panel containing info rows.

    Args:
        title: Card title (will be dim)
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
    # Create content from info rows with proper spacing
    content = Group(*create_info_rows_with_spacing(rows))

    # Build title with optional subtitle, using dim style for card headings
    if subtitle:
        title_text = f"[dim]{title} ({subtitle})[/dim]"
    else:
        title_text = f"[dim]{title}[/dim]"

    return Panel(
        content,
        title=title_text,
        title_align="left",
        border_style=get_card_border_style(),
        padding=get_card_padding(),
        width=width,
    )


def create_detail_card(
    title: str,
    rows: Sequence[tuple[str, "str | Text"]],
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
        width=get_detail_card_width(),
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
    # End of Selectio
