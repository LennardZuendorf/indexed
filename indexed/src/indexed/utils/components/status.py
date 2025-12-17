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
        """
        Create an OperationStatus tied to a Rich console, a human-facing operation label, and optional INFO-log capture.
        
        Parameters:
            console (Console): Rich Console instance used to render the live status.
            operation_desc (str): Short description of the operation shown before status messages (e.g., "Searching", "Indexing").
            capture_logs (bool): If True, INFO-level log messages will be captured and forwarded to the status updates.
        """
        self.console = console
        self.operation_desc = operation_desc
        self.capture_logs = capture_logs
        self._status = None
        self._sink_id = None
        self._current_message = "Starting..."
        self._start_time = None

    def __enter__(self) -> "OperationStatus":
        """
        Enter the context manager and start the live status spinner and message updates.
        
        Sets the start timestamp, creates and enters the Rich status spinner initialized with the current message, and registers INFO log capture for status updates when enabled.
        
        Returns:
            self (OperationStatus): The context manager instance.
        """
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
        """
        Refreshes the active status line to show the current formatted message.
        
        No-op if the status display is not active.
        """
        if self._status:
            formatted = self._format_status_message(self._current_message)
            self._status.update(formatted)

    def update(self, message: str, force_render: bool = False) -> None:
        """
        Set the current status message and refresh the live spinner display.
        
        Parameters:
            message (str): Status text to show (exclude the operation label).
            force_render (bool): If True, pause briefly after updating to ensure the change is visible on fast operations.
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
        """
        Stop the status spinner, ensure it met the minimum display time, disable log capture, and print a final completion message.
        
        Ensures the spinner was visible for at least MIN_DISPLAY_TIME, disables INFO log capture if enabled, stops the spinner display, prints either the success or failure message, and then emits a blank line.
        
        Parameters:
            success (bool): If True, print `success_message`; if False, print `failure_message`.
            success_message (str): Message to print when `success` is True.
            failure_message (str): Message to print when `success` is False.
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
        """
        Exit the OperationStatus context and stop the live status display.
        
        Disables INFO log capture if it is active and forwards any context-manager exit arguments to the underlying Rich status object's __exit__ to stop the spinner and clean up.
        
        Parameters:
            *args: Exception information (exc_type, exc_value, traceback) from the context-manager protocol, forwarded to the underlying status __exit__.
        """
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