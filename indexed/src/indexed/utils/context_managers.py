"""Shared context managers for command execution.

This module provides reusable context managers used across CLI commands
to manage output suppression and no-op contexts.
"""

import logging
import warnings
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO

from loguru import logger as loguru_logger


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
def suppress_core_output(redirect_streams: bool = False):
    """Context manager to suppress core logging output.

    Temporarily suppresses:
    - All logging below CRITICAL level
    - Python warnings (deprecation warnings, etc.)
    - Optionally: stdout/stderr output (disabled by default to allow Rich spinners)

    This is useful when running operations that produce verbose logging
    that should be hidden from the user (e.g., when using progress bars).

    Args:
        redirect_streams: If True, also redirect stdout/stderr. Defaults to False
                         to allow Rich console output (spinners, progress bars).

    Example:
        >>> with suppress_core_output():
        ...     # Logging will be suppressed but Rich console works
        ...     logger.info("This won't be shown")
        ...     console.print("This WILL be shown")

    Yields:
        None

    Note:
        The original logging level is restored after exiting the context.
    """
    # Save original logging level
    original_level = logging.getLogger().level

    try:
        # Suppress all standard logging output
        logging.getLogger().setLevel(logging.CRITICAL)

        # Disable loguru output
        loguru_logger.disable("")

        # Suppress Python warnings (deprecation warnings, etc.)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            
            if redirect_streams:
                # Optionally redirect stdout and stderr
                stdout_capture = StringIO()
                stderr_capture = StringIO()
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    yield
            else:
                # Don't redirect streams - allow Rich console output
                yield

    finally:
        # Restore original logging level
        logging.getLogger().setLevel(original_level)
        # Re-enable loguru
        loguru_logger.enable("")
