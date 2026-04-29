"""Exception hierarchy for indexed-config."""

from __future__ import annotations


class IndexedError(Exception):
    """Base exception for all indexed errors."""


class ConfigurationError(IndexedError):
    """Base exception for configuration-related errors."""


class ConfigValidationError(ConfigurationError):
    """Raised when config validation fails for a registered spec."""

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Invalid config for '{path}': {detail}")


class StorageError(IndexedError):
    """Base exception for storage-related errors."""


class StorageConflictError(StorageError):
    """Raised when local and global storage conflict."""
