# Indexed Config package (unversioned)

from .service import ConfigService, ValidationResult, get_config, reload
from .provider import Provider
from .errors import (
    IndexedError,
    ConfigurationError,
    ConfigValidationError,
    StorageError,
    StorageConflictError,
)
from .storage import (
    StorageMode,
    StorageResolver,
    get_global_root,
    get_local_root,
    get_collections_path,
    get_caches_path,
    has_local_config,
    has_global_config,
    ensure_storage_dirs,
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
