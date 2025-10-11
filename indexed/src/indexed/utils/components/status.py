"""Interactive status component for long-running operations.

This module provides a context manager for showing live status updates
with a spinner during operations like search.
"""

from rich.console import Console
from ..logging import enable_status_capture, disable_status_capture

from .theme import ACCENT_STYLE


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
    
    def __init__(self, console: Console, operation_desc: str, capture_logs: bool = True):
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
    
    def __enter__(self) -> "OperationStatus":
        """Enter context and start the status display."""
        # Start spinner with initial message
        self._update_display()
        self._status = self.console.status(
            self._format_status_message(self._current_message),
            spinner="dots"  # Clean, minimal spinner
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
        return f"[{ACCENT_STYLE}]{self.operation_desc}[/{ACCENT_STYLE}]: {message}"
    
    def _update_display(self) -> None:
        """Update the spinner display with current message."""
        if self._status:
            formatted = self._format_status_message(self._current_message)
            self._status.update(formatted)
    
    def update(self, message: str) -> None:
        """Update the status message.
        
        Args:
            message: New status message to display (without operation description)
        """
        # Store the new message and update display
        self._current_message = message.strip()
        self._update_display()
    
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
