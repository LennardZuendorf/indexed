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
        """
        Provide the context manager instance without performing any action.
        
        Returns:
            self: The same NoOpContext instance to be used within the `with` statement.
        """
        return self

    def __exit__(self, *args):
        """Exit the context (no-op)."""
        pass


@contextmanager
def suppress_core_output(redirect_streams: bool = False):
    """
    Temporarily suppress core logging, disable loguru logging, and ignore Python warnings; optionally redirect stdout and stderr for the duration of the context.
    
    When used as a context manager, sets the root logging level to CRITICAL, disables loguru, and suppresses warnings; on exit it restores the original logging level and re-enables loguru.
    
    Parameters:
        redirect_streams (bool): If True, redirect stdout and stderr to in-memory buffers for the duration of the context. Defaults to False to allow Rich console output (spinners, progress bars).
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