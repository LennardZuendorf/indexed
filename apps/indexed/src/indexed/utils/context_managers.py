"""Shared context managers for command execution.

This module provides reusable context managers used across CLI commands
to manage output suppression and no-op contexts.
"""

import logging
import warnings
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
    Temporarily suppress verbose logging while preserving WARNING/ERROR output.

    Reconfigures both standard logging and loguru to WARNING level (instead of
    disabling entirely) so that parsing errors and warnings still surface.
    On exit, restores the original logging configuration.

    Parameters:
        redirect_streams (bool): If True, redirect stdout and stderr to in-memory buffers for the duration of the context. Defaults to False to allow Rich console output (spinners, progress bars).
    """
    # Save original logging level
    original_level = logging.getLogger().level

    # Save and suppress ALL docling/docling_core loggers (child loggers may
    # have their own handlers that bypass the parent level).
    saved_docling_levels: dict[str, int] = {}
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith(("docling", "docling_core")):
            lg = logging.getLogger(name)
            saved_docling_levels[name] = lg.level
    # Also include the root "docling" logger itself
    docling_root = logging.getLogger("docling")
    saved_docling_levels.setdefault("docling", docling_root.level)

    # Save current loguru min level so we can restore it
    from indexed.utils.logging import _configure_loguru

    try:
        # Suppress standard logging below WARNING
        logging.getLogger().setLevel(logging.WARNING)

        # Suppress all docling loggers (format-mismatch noise); only surface ERRORs
        for name in saved_docling_levels:
            logging.getLogger(name).setLevel(logging.ERROR)

        # Reconfigure loguru to WARNING level instead of disabling entirely,
        # so parsing ERRORs and WARNINGs still surface
        _configure_loguru("WARNING")

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
        for name, level in saved_docling_levels.items():
            logging.getLogger(name).setLevel(level)
        # Restore loguru to its previous configuration
        from indexed.utils.logging import _cli_log_level

        _configure_loguru(_cli_log_level)
