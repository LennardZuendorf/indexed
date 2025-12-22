"""Key-Value Panel Component.

A reusable component that combines Table.grid() inside Panel for clean
key-value displays with proper alignment across the CLI.
"""

from typing import Sequence

from rich import box
from rich.panel import Panel
from rich.table import Table

from .theme import (
    get_label_style,
    get_card_border_style,
    get_value_style,
    get_heading_style,
    get_secondary_style,
)


def _truncate(value: str, max_len: int) -> str:
    """
    Truncates a string to a maximum length, appending "..." when truncation occurs.

    Parameters:
        value (str): The input string to truncate.
        max_len (int): Maximum allowed length of the returned string. When truncation occurs, the returned string's length will equal `max_len` (including the appended ellipsis).

    Returns:
        str: The original string if its length is less than or equal to `max_len`, otherwise a truncated string ending with "...".
    """
    if len(value) <= max_len:
        return value
    if max_len <= 0:
        return ""
    if max_len < 3:
        # Too small for ellipsis, just truncate without it
        return value[:max_len]
    return value[: max_len - 3] + "..."


def create_key_value_panel(
    title: str,
    rows: Sequence[tuple[str, str, str] | tuple[str, str]],
    *,
    category_width: int = 15,
    key_width: int = 25,
    value_max_len: int = 50,
    show_category: bool = True,
    show_headers: bool = True,
    headers: tuple[str, str, str] | tuple[str, str] | None = None,
    expand: bool = True,
) -> Panel:
    """
    Render a Rich Panel showing aligned key/value rows with an optional category column and optional headers.

    Parameters:
        title (str): Panel title displayed on the top border.
        rows (Sequence[tuple[str, str, str] | tuple[str, str]]): Iterable of row tuples. In 3-column mode each row is (category, key, value); in 2-column mode each row is (key, value). When show_category is True a 2-tuple is treated as (key, value) with an empty category; when show_category is False a 3-tuple ignores the category.
        category_width (int): Fixed width (characters) for the category column.
        key_width (int): Fixed width (characters) for the key column.
        value_max_len (int): Maximum length for rendered values; longer values are truncated and end with an ellipsis.
        show_category (bool): Show a category column (three-column layout) when True; otherwise render two columns (key, value).
        show_headers (bool): Render a muted header row above the data when True.
        headers (tuple[str, ...] | None): Custom header labels. Expected length is 3 for three-column mode or 2 for two-column mode; defaults to ("source", "key", "value") or ("key", "value") respectively.
        expand (bool): Whether the panel should expand to fill available width.

    Returns:
        Panel: A styled Rich Panel containing a fixed-width, non-wrapping grid of the provided rows with applied heading, label, and border styles.
    """
    grid = Table.grid(padding=(0, 2), expand=expand)

    if show_category:
        # Category column: blue
        grid.add_column(style=get_label_style(), width=category_width, no_wrap=True)
    # Key column: bold white
    grid.add_column(style=get_heading_style(), width=key_width, no_wrap=True)
    # Value column: white (not muted)
    grid.add_column(style=get_value_style(), no_wrap=True)

    # Add header row if enabled (using Text objects to fully override column styles)
    if show_headers and rows:
        from rich.text import Text

        # Grey color for headers - must set explicit color to override column style
        header_style = get_secondary_style()

        if show_category:
            default_headers = ("source", "key", "value")
            h = headers if headers and len(headers) == 3 else default_headers
            # Use Text objects with explicit grey color to override column styles
            grid.add_row(
                Text(h[0], style=header_style),
                Text(h[1], style=header_style),
                Text(h[2], style=header_style),
            )
            # Empty separator row
            grid.add_row("", "", "")
        else:
            default_headers = ("key", "value")
            h = headers if headers and len(headers) == 2 else default_headers
            grid.add_row(
                Text(h[0], style=header_style),
                Text(h[1], style=header_style),
            )
            # Empty separator row
            grid.add_row("", "")

    for row in rows:
        if show_category:
            if len(row) == 3:
                category, key, value = row
            else:
                # Handle 2-tuple when show_category is True (use empty category)
                category = ""
                key, value = row
            truncated = _truncate(str(value), value_max_len)
            grid.add_row(category, key, truncated)
        else:
            # 2-column mode
            if len(row) == 3:
                _, key, value = row  # Ignore category
            else:
                key, value = row
            truncated = _truncate(str(value), value_max_len)
            grid.add_row(key, truncated)

    return Panel(
        grid,
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style=get_card_border_style(),
        expand=expand,
    )


def create_simple_key_value_panel(
    title: str,
    rows: Sequence[tuple[str, str]],
    *,
    key_width: int = 50,
    value_max_len: int = 30,
    show_headers: bool = True,
    headers: tuple[str, str] | None = None,
    expand: bool = True,
) -> Panel:
    """Create a simple 2-column key-value panel.

    A convenience wrapper for create_key_value_panel with show_category=False.

    Args:
        title: Panel title
        rows: List of (key, value) tuples
        key_width: Fixed width for key column
        value_max_len: Maximum value length before truncation
        show_headers: Whether to show column headers
        headers: Custom header labels (key, value)
        expand: Whether to expand to fill width

    Returns:
        Rich Panel with 2-column layout

    Example:
        >>> rows = [
        ...     ("/Users/dev/project", "local"),
        ...     ("/Users/dev/other", "global"),
        ... ]
        >>> panel = create_simple_key_value_panel("Workspace Preferences", rows)
    """
    return create_key_value_panel(
        title,
        rows,
        key_width=key_width,
        value_max_len=value_max_len,
        show_category=False,
        show_headers=show_headers,
        headers=headers,
        expand=expand,
    )
