# Indexed Config package (unversioned)

from .errors import (
    ConfigurationError,
    ConfigValidationError,
    IndexedError,
    StorageConflictError,
    StorageError,
)
from .provider import Provider
from .service import ConfigService, ValidationResult, get_config, reload
from .storage import (
    StorageMode,
    StorageResolver,
    ensure_storage_dirs,
    get_caches_path,
    get_collections_path,
    get_global_root,
    get_local_root,
    has_global_config,
    has_local_config,
)

__all__ = [
    # Core service
    "ConfigService",
    "ValidationResult",
    "get_config",
    "reload",
    "Provider",
    # Error hierarchy
    "IndexedError",
    "ConfigurationError",
    "ConfigValidationError",
    "StorageError",
    "StorageConflictError",
    # Storage (public API)
    "StorageMode",
    "StorageResolver",
    "get_global_root",
    "get_local_root",
    "get_collections_path",
    "get_caches_path",
    "has_local_config",
    "has_global_config",
    "ensure_storage_dirs",
]
