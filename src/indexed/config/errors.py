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


class SchemaVersionError(ConfigurationError):
    """Raised when a config or profile file declares an unusable schema version.

    Version ``"2"`` is current. ``"1"``/absent is accepted only when the file
    carries none of the keys the storage-mode collapse removed; when it does,
    this names them so the fix is obvious. Anything else is rejected outright.
    """

    def __init__(self, path: object, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: {detail}")


class WorkspaceResolutionError(ConfigurationError):
    """Raised when a workspace or its profile cannot be resolved.

    Resolution fails CLOSED: an explicit workspace that is not an existing
    directory, or a profile that is found but unparseable, must raise rather
    than degrade to an unfiltered global view.
    """


def missing_wiring_error(component: str) -> ConfigurationError:
    """Error for a DI dependency the app composition root failed to inject."""
    return ConfigurationError(
        f"{component} must be injected by the app layer; see indexed.composition"
    )
