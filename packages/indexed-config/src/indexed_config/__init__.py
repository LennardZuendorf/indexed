# Indexed Config package (unversioned)

from .service import ConfigService
from .provider import Provider
from .store import TomlStore
from .storage import (
    StorageMode,
    StorageResolver,
    get_global_root,
    get_local_root,
    get_config_path,
    get_env_path,
    get_data_root,
    get_collections_path,
    get_caches_path,
    has_local_storage,
    has_global_storage,
    has_local_config,
    has_global_config,
    ensure_storage_dirs,
    get_resolver,
    reset_resolver,
)

__all__ = [
    "ConfigService",
    "Provider",
    "TomlStore",
    # Storage module exports
    "StorageMode",
    "StorageResolver",
    "get_global_root",
    "get_local_root",
    "get_config_path",
    "get_env_path",
    "get_data_root",
    "get_collections_path",
    "get_caches_path",
    "has_local_storage",
    "has_global_storage",
    "has_local_config",
    "has_global_config",
    "ensure_storage_dirs",
    "get_resolver",
    "reset_resolver",
]
