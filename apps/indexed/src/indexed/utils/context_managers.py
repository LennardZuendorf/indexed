"""Shared context managers for command execution.

Provides ``NoOpContext`` for use in verbose-mode paths where a command would
otherwise enter a Rich progress context. The previous ``suppress_core_output``
helper was removed — third-party log noise is now handled by the single-sink
Loguru architecture in ``utils.logger`` (see ``packages/utils/CLAUDE.md``).
"""


class NoOpContext:
    """No-op context manager for verbose mode (no spinner).

    Used when verbose output is enabled and a command should skip the Rich
    progress UI but still satisfy a ``with`` block.

    Example:
        >>> with NoOpContext():
        ...     print("This runs without any spinner wrapping it")
    """

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None
