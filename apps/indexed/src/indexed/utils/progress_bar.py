"""Rich progress bar integration for CLI operations.

This module provides:
- RichPhasedProgress: Multi-stage progress display implementing PhasedProgressCallback
- PlainPhasedProgress: Non-interactive fallback for piped/CI output
- create_phased_progress(): Factory that picks the right implementation
"""

import time
from typing import Optional, Dict

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    SpinnerColumn,
    TaskID,
)

from indexed.utils.components.theme import (
    get_accent_style,
    get_heading_style,
    get_default_style,
    get_dim_style,
)
from indexed.utils.console import console, is_interactive


class RichPhasedProgress:
    """Rich Progress-based implementation of PhasedProgressCallback.

    Displays multiple named phases with individual progress bars or spinners.
    Completed phases show a checkmark with elapsed time.

    Example output:
        Creating collection "jira-issues"...

          ✓ Loading embedding model              0.4s
          ● Fetching documents     ━━━━━━━━━━━╸  137/500  27%  0:00:42
            Generating embeddings                waiting...
            Building FAISS index                 waiting...
    """

    def __init__(self, title: str = "") -> None:
        self._title = title
        self._accent = get_accent_style()
        self._dim = get_dim_style()
        self._default = get_default_style()
        self._progress = Progress(
            SpinnerColumn(style=self._accent),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                bar_width=20,
                complete_style=self._default,
                finished_style=self._default,
                pulse_style=self._dim,
            ),
            TextColumn(
                f"[{self._default}]{{task.percentage:>3.0f}}%[/{self._default}]"
            ),
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
            task_id = self._tasks[name]
            if total is not None:
                self._progress.update(task_id, total=total, completed=0)
            self._progress.update(
                task_id,
                description=f"  {name}",
                visible=True,
            )
        else:
            task_id = self._progress.add_task(
                f"  {name}",
                total=total,
            )
            self._tasks[name] = task_id

    def advance(self, name: str, amount: int = 1) -> None:
        """Advance the named phase by amount items."""
        if not self._started or name not in self._tasks:
            return
        self._progress.advance(self._tasks[name], advance=amount)

    def finish_phase(self, name: str) -> None:
        """Mark the named phase as complete with checkmark and elapsed time."""
        if not self._started or name not in self._tasks:
            return

        task_id = self._tasks[name]
        elapsed = time.monotonic() - self._start_times.get(name, time.monotonic())
        elapsed_str = f"{elapsed:.1f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"

        task = self._progress.tasks[task_id]
        if task.total is not None:
            self._progress.update(task_id, completed=task.total)

        self._progress.update(
            task_id,
            description=f"  [{self._accent}]✓[/{self._accent}] {name}  [{self._dim}]{elapsed_str}[/{self._dim}]",
        )

    def log(self, message: str) -> None:
        """Display a log message within the progress context."""
        if self._started:
            self._progress.console.print(f"    [{self._dim}]{message}[/{self._dim}]")


class PlainPhasedProgress:
    """Non-interactive fallback implementing PhasedProgressCallback.

    Outputs plain text lines like:
        [1] Loading model...
        [2] Fetching documents...
    """

    def __init__(self) -> None:
        self._phase_order: list[str] = []

    def __enter__(self) -> "PlainPhasedProgress":
        return self

    def __exit__(self, *args) -> None:
        pass

    def start_phase(self, name: str, total: Optional[int] = None) -> None:
        if name not in self._phase_order:
            self._phase_order.append(name)
        idx = self._phase_order.index(name) + 1
        print(f"[{idx}] {name}...")

    def advance(self, name: str, amount: int = 1) -> None:
        pass

    def finish_phase(self, name: str) -> None:
        pass

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


def build_progress_title(verb: str, collection: str, source_display: str = "") -> str:
    """Build a consistently styled title for phased progress sections.

    Args:
        verb: Action word, e.g. "Creating" or "Updating"
        collection: Collection name (highlighted in accent color)
        source_display: Human-readable source type, e.g. "Local Files" (optional)

    Returns:
        Rich markup string for use as a progress section title.
    """
    heading = get_heading_style()
    accent = get_accent_style()
    type_part = f"{source_display} collection" if source_display else "collection"
    return (
        f"[{heading}]{verb} {type_part}: [{accent}]{collection}[/{accent}][/{heading}]"
    )
