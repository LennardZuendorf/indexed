# Indexed Config package (unversioned)

from .service import ConfigService, ValidationResult, get_config, reload
from .provider import Provider
from .errors import (
    IndexedError,
    ConfigurationError,
    ConfigValidationError,
    StorageError,
    SchemaVersionError,
    WorkspaceResolutionError,
)
from .storage import (
    get_global_root,
    get_collections_path,
    get_caches_path,
    get_global_collections_path,
    get_global_caches_path,
    has_global_config,
    ensure_storage_dirs,
)
from .discovery import CANONICAL_NAME, LEGACY_RELPATH, find_profile
from .workspace import (
    WorkspaceProfile,
    WorkspaceScope,
    clear_scope_cache,
    resolve_scope,
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
    "SchemaVersionError",
    "WorkspaceResolutionError",
    # Storage (public API) — one global root
    "get_global_root",
    "get_collections_path",
    "get_caches_path",
    "get_global_collections_path",
    "get_global_caches_path",
    "has_global_config",
    "ensure_storage_dirs",
    # Workspace profile + scope
    "CANONICAL_NAME",
    "LEGACY_RELPATH",
    "find_profile",
    "WorkspaceProfile",
    "WorkspaceScope",
    "clear_scope_cache",
    "resolve_scope",
]
