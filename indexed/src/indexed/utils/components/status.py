"""Interactive status component for long-running operations.

This module provides a context manager for showing live status updates
with a spinner during operations like search.
"""

import time

from rich.console import Console
from ..logging import enable_status_capture, disable_status_capture

from .theme import get_accent_style


class OperationStatus:
    """Context manager for displaying operation progress with spinner.

    Shows a live spinner with an operation description and dynamic status messages.
    Format: [spinner] [Operation]: [Log Message]
    Uses cyan accent styling consistent with the design system.
    Automatically captures INFO logs and displays them in the spinner.

    Example:
        >>> with OperationStatus(console, "Searching") as status:
        ...     # Logs automatically appear as:
        ...     # [spinner] Searching: Found 3 collections
        ...     # [spinner] Searching: Processing files
    """

    # Minimum time the spinner should be visible (in seconds)
    MIN_DISPLAY_TIME = 0.5

    def __init__(
        self, console: Console, operation_desc: str, capture_logs: bool = True
    ):
        """Initialize the status display.

        Args:
            console: Rich console instance to use for display
            operation_desc: Description of the operation (e.g., "Searching", "Indexing")
            capture_logs: If True, capture INFO logs and show as status updates
        """
        self.console = console
        self.operation_desc = operation_desc
        self.capture_logs = capture_logs
        self._status = None
        self._sink_id = None
        self._current_message = "Starting..."
        self._start_time = None

    def __enter__(self) -> "OperationStatus":
        """Enter context and start the status display."""
        # Track when we started for minimum display time
        self._start_time = time.time()
        
        # Start spinner with initial message
        self._status = self.console.status(
            self._format_status_message(self._current_message),
            spinner="dots",  # Clean, minimal spinner
            refresh_per_second=12.5,  # Ensure smooth updates
        )
        self._status.__enter__()

        # Enable INFO log capture for status updates
        if self.capture_logs:
            self._sink_id = enable_status_capture(self.update)

        return self

    def _format_status_message(self, message: str) -> str:
        """Format the full status message with operation description.

        Args:
            message: The log message to display

        Returns:
            Formatted string: [Operation]: [Message]
        """
        return f"[{get_accent_style()}]{self.operation_desc}[/{get_accent_style()}]: {message}"

    def _update_display(self) -> None:
        """Update the spinner display with current message."""
        if self._status:
            formatted = self._format_status_message(self._current_message)
            self._status.update(formatted)

    def update(self, message: str, force_render: bool = False) -> None:
        """Update the status message.

        Args:
            message: New status message to display (without operation description)
            force_render: If True, force a brief pause to ensure the message is visible
        """
        # Store the new message and update display
        self._current_message = message.strip()
        self._update_display()
        
        # Force render to ensure the spinner is visible for fast operations
        if force_render and self._status:
            time.sleep(0.15)  # Brief pause to ensure spinner is visible

    def complete(
        self,
        success: bool = True,
        success_message: str = "Finished, Collection Created",
        failure_message: str = "Aborted, Creation Failed",
    ) -> None:
        """Stop spinner and show completion message.

        Call this before exiting the context to show a clean completion state
        instead of just stopping the spinner.

        Args:
            success: True shows success_message, False shows failure_message
            success_message: Message to show on success (default: "Finished, Collection Created")
            failure_message: Message to show on failure (default: "Aborted, Creation Failed")
        """
        # Ensure spinner was visible for minimum time
        if self._start_time is not None:
            elapsed = time.time() - self._start_time
            if elapsed < self.MIN_DISPLAY_TIME:
                time.sleep(self.MIN_DISPLAY_TIME - elapsed)
        
        # Disable log capture first
        if self._sink_id is not None:
            disable_status_capture()
            self._sink_id = None

        # Stop the spinner
        if self._status:
            self._status.stop()
            self._status = None

        # Print completion message (no icons - icons go on final result)
        if success:
            self.console.print(success_message)
        else:
            self.console.print(failure_message)

        self.console.print()  # Whitespace before final result message

    def __exit__(self, *args) -> None:
        """Exit context and stop the status display."""
        # Disable INFO log capture
        if self._sink_id is not None:
            disable_status_capture()
            self._sink_id = None

        # Stop status display
        if self._status:
            self._status.__exit__(*args)


# Backwards compatibility alias
SearchStatus = OperationStatus

__all__ = ["OperationStatus", "SearchStatus"]
