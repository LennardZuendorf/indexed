"""Rich progress bar integration for CLI operations.

This module provides:
- RichPhasedProgress: Multi-stage progress display implementing PhasedProgressCallback
- PlainPhasedProgress: Non-interactive fallback for piped/CI output
- Legacy progress bar wrappers for backward compatibility
"""

import time
from typing import Callable, Optional, Dict
from contextlib import contextmanager

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    SpinnerColumn,
    TaskProgressColumn,
    TaskID,
)

from indexed.utils.components.theme import (
    get_label_style,
    get_default_style,
)
from indexed.utils.console import console, is_interactive


class RichPhasedProgress:
    """Rich Progress-based implementation of PhasedProgressCallback.

    Displays multiple named phases with individual progress bars or spinners.
    Completed phases show a ✓ checkmark with elapsed time.

    Example output:
        Creating collection "jira-issues"...

          ✓ Loading embedding model              0.4s
          ● Fetching documents     ━━━━━━━━━━━╸  137/500  27%  0:00:42
            Parsing & chunking                   waiting...
            Generating embeddings                waiting...
            Building FAISS index                 waiting...
    """

    def __init__(self, title: str = "") -> None:
        self._title = title
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=20),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self._tasks: Dict[str, TaskID] = {}
        self._start_times: Dict[str, float] = {}
        self._started = False

    def __enter__(self) -> "RichPhasedProgress":
        if self._title:
            console.print(f"\n{self._title}\n")
        self._progress.start()
        self._started = True
        return self

    def __exit__(self, *args) -> None:
        self._progress.stop()
        self._started = False

    def start_phase(self, name: str, total: Optional[int] = None) -> None:
        """Begin a named phase with progress bar (if total given) or spinner."""
        if not self._started:
            return

        self._start_times[name] = time.monotonic()

        if name in self._tasks:
            # Phase already exists — update total and reset
            task_id = self._tasks[name]
            if total is not None:
                self._progress.update(task_id, total=total, completed=0)
            self._progress.update(
                task_id,
                description=f"  [bold #2581C4]●[/bold #2581C4] {name}",
                visible=True,
            )
        else:
            task_id = self._progress.add_task(
                f"  [bold #2581C4]●[/bold #2581C4] {name}",
                total=total,
            )
            self._tasks[name] = task_id

    def advance(self, name: str, amount: int = 1) -> None:
        """Advance the named phase by amount items."""
        if not self._started or name not in self._tasks:
            return
        self._progress.advance(self._tasks[name], advance=amount)

    def finish_phase(self, name: str) -> None:
        """Mark the named phase as complete with ✓ and elapsed time."""
        if not self._started or name not in self._tasks:
            return

        task_id = self._tasks[name]
        elapsed = time.monotonic() - self._start_times.get(name, time.monotonic())
        elapsed_str = f"{elapsed:.1f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"

        # Mark complete
        task = self._progress.tasks[task_id]
        if task.total is not None:
            self._progress.update(task_id, completed=task.total)

        self._progress.update(
            task_id,
            description=f"  [green]✓[/green] {name}  [dim]{elapsed_str}[/dim]",
        )

    def log(self, message: str) -> None:
        """Display a log message within the progress context."""
        if self._started:
            self._progress.console.print(f"    [dim]{message}[/dim]")


class PlainPhasedProgress:
    """Non-interactive fallback implementing PhasedProgressCallback.

    Outputs plain text lines like:
        [1/5] Loading model...
        [2/5] Fetching documents... 137/500
    """

    def __init__(self) -> None:
        self._phase_order: list[str] = []
        self._totals: Dict[str, Optional[int]] = {}

    def __enter__(self) -> "PlainPhasedProgress":
        return self

    def __exit__(self, *args) -> None:
        pass

    def start_phase(self, name: str, total: Optional[int] = None) -> None:
        if name not in self._phase_order:
            self._phase_order.append(name)
        self._totals[name] = total
        idx = self._phase_order.index(name) + 1
        print(f"[{idx}] {name}...")

    def advance(self, name: str, amount: int = 1) -> None:
        pass  # No inline updates in plain mode

    def finish_phase(self, name: str) -> None:
        pass  # Already printed start

    def log(self, message: str) -> None:
        print(f"    {message}")


def create_phased_progress(
    title: str = "",
) -> "RichPhasedProgress | PlainPhasedProgress":
    """Create the appropriate phased progress implementation.

    Returns RichPhasedProgress for interactive terminals,
    PlainPhasedProgress for piped/CI environments.
    """
    if is_interactive():
        return RichPhasedProgress(title=title)
    return PlainPhasedProgress()


# --- LEGACY PROGRESS BAR SUPPORT ---
# These functions are kept for backward compatibility with existing commands.

# Global progress tracker for CLI integration
_cli_progress = None
_cli_console = None


def set_cli_progress(progress, cli_console):
    """Set the global CLI progress and console for integration."""
    global _cli_progress, _cli_console
    _cli_progress = progress
    _cli_console = cli_console


def clear_cli_progress():
    """Clear the global CLI progress."""
    global _cli_progress, _cli_console
    _cli_progress = None
    _cli_console = None


def create_progress_callback(progress: Progress, task_id: int) -> Callable:
    """Create a callback that updates a Rich Progress task from ProgressUpdate objects."""

    def callback(update):
        if update.total and update.total > 0:
            completed = int((update.current / update.total) * 100)
            progress.update(
                task_id, completed=completed, description=f"[bold blue]{update.message}"
            )
        else:
            progress.update(task_id, description=f"[bold blue]{update.message}")

    return callback


def create_progress_update_callback(operation_status) -> Callable:
    """Create a callback that applies ProgressUpdate values to an OperationStatus display."""
    from core.v1.engine.services.models import ProgressUpdate

    def callback(update: ProgressUpdate):
        if update.total == 0:
            msg = "No changes detected"
        elif update.total and update.total > 0:
            msg = f"{update.stage.capitalize()}: {update.current}/{update.total} documents"
        else:
            msg = update.message

        operation_status.update(msg)

    return callback


def create_standard_progress() -> Progress:
    """Create a standardized progress bar with consistent styling."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold #2581C4]{task.description}"),
        BarColumn(
            complete_style="bold bright_yellow",
            finished_style="bold bright_yellow",
        ),
        TextColumn("[bold bright_yellow]{task.percentage:>3.0f}%"),
        TextColumn("[bold white]{task.time_remaining}"),
        console=console,
        transient=False,
    )


@contextmanager
def create_operation_progress(operation_desc: str, total: int = 100):
    """Context manager for standardized operation progress tracking."""
    start_time = time.time()

    # Extract collection name from operation_desc
    if "[" in operation_desc and "]" in operation_desc:
        import re

        match = re.search(r'"([^"]+)"', operation_desc)
        if match:
            collection_name = match.group(1)
        else:
            match = re.search(r"\[.*?\](.*?)\[/.*?\]", operation_desc)
            collection_name = match.group(1).strip() if match else operation_desc
    else:
        collection_name = operation_desc

    with create_standard_progress() as progress:
        set_cli_progress(progress, console)

        try:
            task_id = progress.add_task(operation_desc, total=total)

            styled_name = (
                f"[{get_label_style()}]{collection_name}[/{get_label_style()}]"
            )
            progress.update(
                task_id,
                description=f"{styled_name}[{get_default_style()}]: Starting...[/{get_default_style()}]",
            )

            callback = create_progress_callback(progress, task_id)

            yield progress, task_id, callback

            elapsed = time.time() - start_time
            if elapsed < 0.2:
                styled_name = (
                    f"[{get_label_style()}]{collection_name}[/{get_label_style()}]"
                )
                progress.update(
                    task_id,
                    description=f"✓ {styled_name}[{get_default_style()}]: Complete[/{get_default_style()}]",
                )
                time.sleep(0.1)
            else:
                styled_name = (
                    f"[{get_label_style()}]{collection_name}[/{get_label_style()}]"
                )
                progress.update(
                    task_id,
                    completed=total,
                    description=f"✓ {styled_name}[{get_default_style()}]: Complete[/{get_default_style()}]",
                )
                time.sleep(0.2)

        finally:
            clear_cli_progress()
