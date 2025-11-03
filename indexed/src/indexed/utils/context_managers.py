"""Shared context managers for command execution.

This module provides reusable context managers used across CLI commands
to manage output suppression and no-op contexts.
"""

import logging
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO


class NoOpContext:
    """No-op context manager for verbose mode (no spinner).

    Used when verbose output is enabled and we don't want to use
    a progress spinner or suppress output.

    Example:
        >>> with NoOpContext():
        ...     print("This will be displayed")
    """

    def __enter__(self):
        """Enter the context (no-op)."""
        return self

    def __exit__(self, *args):
        """Exit the context (no-op)."""
        pass


@contextmanager
def suppress_core_output():
    """Context manager to suppress all core logging and output.

    Temporarily suppresses:
    - All logging below CRITICAL level
    - stdout output
    - stderr output

    This is useful when running operations that produce verbose output
    that should be hidden from the user (e.g., when using progress bars).

    Example:
        >>> with suppress_core_output():
        ...     # Any logging or print statements here will be suppressed
        ...     logger.info("This won't be shown")
        ...     print("This won't be shown either")

    Yields:
        None

    Note:
        The original logging level is restored after exiting the context.
    """
    # Capture all output streams
    stdout_capture = StringIO()
    stderr_capture = StringIO()

    # Save original logging level
    original_level = logging.getLogger().level

    try:
        # Suppress all logging output
        logging.getLogger().setLevel(logging.CRITICAL)

        # Redirect stdout and stderr
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            yield

    finally:
        # Restore original logging level
        logging.getLogger().setLevel(original_level)
