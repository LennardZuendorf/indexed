from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn


# Singleton consoles
console = Console()
err_console = Console(stderr=True)


def human_size(n: Optional[int]) -> str:
    if not n:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(n)
    for u in units:
        if size < 1024.0:
            return f"{size:.1f}{u}"
        size /= 1024.0
    return f"{size:.1f}EB"


def success_panel(title: str, body: str | None = None) -> Panel:
    text = body or ""
    return Panel.fit(text, title=title, border_style="green")


def error_panel(title: str, body: str | None = None) -> Panel:
    text = body or ""
    return Panel.fit(text, title=title, border_style="red")


def make_table(*columns: str, header_style: str = "bold", show_header: bool = True) -> Table:
    table = Table(show_header=show_header, header_style=header_style)
    for col in columns:
        table.add_column(col)
    return table


@contextmanager
def spinner(description: str = "Processing…") -> Iterator[Progress]:
    """A transient spinner that can be updated with new descriptions.

    Usage:
        with spinner("Preparing…") as prog:
            task = prog.add_task(description="Preparing…", total=None)
            # later: prog.update(task, description="Indexing…")
    """
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        expand=False,
    )
    with progress:
        task_id = progress.add_task(description=description, total=None)
        try:
            yield progress
        finally:
            # allow context exit to clear spinner
            try:
                progress.remove_task(task_id)
            except Exception:
                pass


@contextmanager
def transient_spinner(description: str = "Processing…") -> Iterator[Progress]:
    """A simple transient spinner for operations.

    Usage:
        with transient_spinner("Creating collection...") as spinner:
            # do work
            pass
    """
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        expand=False,
    )
    with progress:
        task_id = progress.add_task(description=description, total=None)
        try:
            yield progress
        finally:
            # allow context exit to clear spinner
            try:
                progress.remove_task(task_id)
            except Exception:
                pass


