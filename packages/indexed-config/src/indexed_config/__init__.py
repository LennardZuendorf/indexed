# Indexed Config package (unversioned)

from .service import ConfigService, ValidationResult
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
