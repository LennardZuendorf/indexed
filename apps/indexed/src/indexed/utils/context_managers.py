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


class _BlockDoclingFilter(logging.Filter):
    """Block docling/docling_core WARNING records at the root logger.

    Installed on the root logger inside ``suppress_core_output`` so that
    docling loggers created *lazily* (after the context is entered) are
    still silenced — even if they carry their own handlers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(("docling", "docling_core")):
            return record.levelno >= logging.CRITICAL
        return True


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

    # Configure docling parent loggers to ERROR — child loggers with NOTSET
    # inherit this, covering loggers created lazily inside the context.
    docling_logger = logging.getLogger("docling")
    docling_core_logger = logging.getLogger("docling_core")
    saved_docling_level = docling_logger.level
    saved_docling_core_level = docling_core_logger.level

    # Root filter catches any docling child logger that has its own handler
    # (bypassing parent level inheritance via propagation to root).
    docling_filter = _BlockDoclingFilter()

    # Save current loguru min level so we can restore it
    from indexed.utils.logging import _cli_log_level, _configure_loguru

    saved_loguru_level = _cli_log_level

    try:
        # Suppress standard logging below WARNING
        logging.getLogger().setLevel(logging.WARNING)

        # Suppress docling loggers and install root filter
        docling_logger.setLevel(logging.ERROR)
        docling_core_logger.setLevel(logging.ERROR)
        logging.getLogger().addFilter(docling_filter)

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
        logging.getLogger().removeFilter(docling_filter)
        docling_logger.setLevel(saved_docling_level)
        docling_core_logger.setLevel(saved_docling_core_level)
        # Restore loguru to its previous configuration
        _configure_loguru(saved_loguru_level)
