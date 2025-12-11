"""Rich progress bar integration for CLI operations.

This module provides progress bar functionality that integrates with the CLI's
Rich-based display system, replacing tqdm with a more integrated approach.
"""

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    SpinnerColumn,
)
from rich.console import Console
import time
from typing import Callable
from contextlib import contextmanager

from indexed.utils.components.theme import (
    get_accent_style,
    get_label_style,
    get_default_style,
)
from indexed.utils.console import console

# Global progress tracker for CLI integration
_cli_progress = None
_cli_console = None


def set_cli_progress(progress, console):
    """Set the global CLI progress and console for integration."""
    global _cli_progress, _cli_console
    _cli_progress = progress
    _cli_console = console


def clear_cli_progress():
    """Clear the global CLI progress."""
    global _cli_progress, _cli_console
    _cli_progress = None
    _cli_console = None


def wrap_generator_with_progress_bar(
    generator, approx_total, progress_bar_name="Processing"
):
    """Wrap generator with Rich progress bar that integrates with CLI spinner."""
    global _cli_progress, _cli_console

    if _cli_progress and _cli_console:
        # Use CLI-integrated progress
        task_id = _cli_progress.add_task(progress_bar_name, total=approx_total)

        for item in generator:
            yield item
            _cli_progress.update(task_id, advance=1)
    else:
        # Fallback to standalone Rich progress
        console = Console()
        with Progress(
            SpinnerColumn(),
            TextColumn(f"{get_accent_style()}]{'{task.description}'}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(f"{get_label_style()}"),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task(progress_bar_name, total=approx_total)

            for item in generator:
                yield item
                progress.update(task_id, advance=1)


def wrap_iterator_with_progress_bar(iterator, progress_bar_name="Processing"):
    """Wrap iterator with Rich progress bar that integrates with CLI spinner."""
    global _cli_progress, _cli_console

    if _cli_progress and _cli_console:
        # Use CLI-integrated progress
        total = len(iterator) if hasattr(iterator, "__len__") else None
        task_id = _cli_progress.add_task(progress_bar_name, total=total)

        for item in iterator:
            yield item
            _cli_progress.update(task_id, advance=1)
    else:
        # Fallback to standalone Rich progress
        console = Console()
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            total = len(iterator) if hasattr(iterator, "__len__") else None
            task_id = progress.add_task(progress_bar_name, total=total)

            for item in iterator:
                yield item
                progress.update(task_id, advance=1)


def create_progress_callback(progress: Progress, task_id: int) -> Callable:
    """
    Create a callback that updates a Rich Progress task from ProgressUpdate objects.
    
    The returned callable accepts an update object with `current`, `total`, and `message`. When `total` is greater than zero it computes completion percentage and updates the task's completed value and description; otherwise it updates the task description with the message only.
    
    Parameters:
        progress (Progress): Rich Progress instance used to update the task.
        task_id (int): ID of the task to update within the Progress instance.
    
    Returns:
        callback (Callable): A function that accepts a ProgressUpdate-like object and applies its values to the specified progress task.
    """

    def callback(update):
        """Update progress bar with structured progress information.

        Args:
            update: ProgressUpdate dataclass with stage, current, total, and message
        """
        # Calculate percentage if total is known
        if update.total and update.total > 0:
            completed = int((update.current / update.total) * 100)
            progress.update(
                task_id, completed=completed, description=f"[bold blue]{update.message}"
            )
        else:
            # Indeterminate progress - just update message
            progress.update(task_id, description=f"[bold blue]{update.message}")

    return callback


def create_progress_update_callback(operation_status) -> Callable:
    """
    Create a callback that applies ProgressUpdate values to an OperationStatus display.
    
    Parameters:
        operation_status: OperationStatus instance to receive formatted status messages.
    
    Returns:
        callback (Callable[[ProgressUpdate], None]): Function that accepts a ProgressUpdate and updates the provided OperationStatus with a human-readable message.
    """
    from core.v1.engine.services.models import ProgressUpdate

    def callback(update: ProgressUpdate):
        """
        Update the provided OperationStatus with a human-readable message derived from a ProgressUpdate.
        
        Formats the message as follows:
        - If update.total == 0: "No changes detected".
        - If update.total > 0: "{Stage}: {current}/{total} documents" (stage capitalized).
        - Otherwise: uses update.message.
        
        Parameters:
            update (ProgressUpdate): Progress information with attributes `stage`, `current`, `total`, and `message`.
        """
        # Handle case where no documents to process (total=0)
        if update.total == 0:
            msg = "No changes detected"
        # Format message with counts if available
        elif update.total and update.total > 0:
            msg = f"{update.stage.capitalize()}: {update.current}/{update.total} documents"
        else:
            # Use provided message for operations without known totals
            msg = update.message

        operation_status.update(msg)

    return callback


# --- CENTRALIZED PROGRESS BAR FACTORIES ---


def create_standard_progress() -> Progress:
    """Create a standardized progress bar with consistent styling.

    This is the main progress bar used by search and update commands.
    Features:
    - Blue accent text for operation description
    - Yellow progress bar and percentage
    - White time remaining
    - Spinner for visual feedback
    - Non-transient (stays visible)

    Returns:
        Configured Progress instance with standard styling
    """
    return Progress(
        SpinnerColumn(),
        TextColumn(
            "[bold #2581C4]{task.description}"
        ),  # Blue accent for operation text
        BarColumn(
            complete_style="bold bright_yellow",  # Yellow progress bar
            finished_style="bold bright_yellow",
        ),
        TextColumn("[bold bright_yellow]{task.percentage:>3.0f}%"),  # Yellow percentage
        TextColumn("[bold white]{task.time_remaining}"),  # White time remaining
        console=console,
        transient=False,  # Keep visible, don't auto-hide
    )


def create_standalone_progress() -> Progress:
    """Create a standalone progress bar for fallback scenarios.

    Used when CLI integration is not available.
    Features:
    - Uses theme colors from components
    - Transient (auto-hides)
    - Basic styling for standalone use

    Returns:
        Configured Progress instance for standalone use
    """
    return Progress(
        SpinnerColumn(),
        TextColumn(f"{get_accent_style()}]{'{task.description}'}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(f"{get_label_style()}"),
        console=Console(),
        transient=True,
    )


@contextmanager
def create_operation_progress(operation_desc: str, total: int = 100):
    """Context manager for standardized operation progress tracking.

    This provides a complete solution for operations that need progress tracking
    with smart timing and completion handling.

    Args:
        operation_desc: Description of the operation being performed
        total: Total progress value (default 100 for percentage)

    Yields:
        Tuple of (progress, task_id, callback) for the operation
    """
    start_time = time.time()

    # Extract collection name from operation_desc for proper styling
    # Handle both plain text and styled text formats
    if "[" in operation_desc and "]" in operation_desc:
        # Extract collection name from styled text like '[white]Updating "collection"[/white]'
        import re

        # Find text between quotes
        match = re.search(r'"([^"]+)"', operation_desc)
        if match:
            collection_name = match.group(1)
        else:
            # Fallback: extract text between brackets
            match = re.search(r"\[.*?\](.*?)\[/.*?\]", operation_desc)
            collection_name = match.group(1).strip() if match else operation_desc
    else:
        # Plain text format
        collection_name = operation_desc

    with create_standard_progress() as progress:
        # Set up CLI progress integration
        set_cli_progress(progress, console)

        try:
            # Add main task for the operation
            task_id = progress.add_task(operation_desc, total=total)

            # Update progress as operation proceeds with proper styling
            # Style: collection name in label style, rest in default style
            styled_name = (
                f"[{get_label_style()}]{collection_name}[/{get_label_style()}]"
            )
            progress.update(
                task_id,
                description=f"{styled_name}[{get_default_style()}]: Starting...[/{get_default_style()}]",
            )

            # Create progress callback
            callback = create_progress_callback(progress, task_id)

            yield progress, task_id, callback

            # Check if operation was fast enough to skip progress display
            elapsed = time.time() - start_time
            if elapsed < 0.2:
                # Operation was too fast, just show completion without progress bar
                # Style: collection name in label style, rest in default style
                styled_name = (
                    f"[{get_label_style()}]{collection_name}[/{get_label_style()}]"
                )
                progress.update(
                    task_id,
                    description=f"✓ {styled_name}[{get_default_style()}]: Complete[/{get_default_style()}]",
                )
                time.sleep(0.1)  # Brief pause to show completion
            else:
                # Operation took long enough, show full progress completion
                # Style: collection name in label style, rest in default style
                styled_name = (
                    f"[{get_label_style()}]{collection_name}[/{get_label_style()}]"
                )
                progress.update(
                    task_id,
                    completed=total,
                    description=f"✓ {styled_name}[{get_default_style()}]: Complete[/{get_default_style()}]",
                )
                time.sleep(0.2)  # Longer pause to show completion

        finally:
            # Clear CLI progress integration
            clear_cli_progress()


def create_simple_spinner(description: str = "Processing…") -> Progress:
    """Create a simple spinner for quick operations.

    Args:
        description: Description text for the spinner

    Returns:
        Configured Progress instance with spinner only
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        expand=False,
    )