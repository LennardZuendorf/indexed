"""Storage path resolution for indexed.

This module provides centralized path resolution for indexed's storage locations,
supporting both global (~/.indexed) and local (./.indexed) storage modes.

The storage hierarchy is:
    ~/.indexed/                    # Global default (HOME)
    ├── config.toml               # Global configuration
    ├── .env                      # Sensitive credentials
    └── data/
        ├── collections/          # Index storage
        └── caches/               # Document caches

    ./.indexed/                    # Local override (when --local used)
    ├── config.toml
    ├── .env
    └── data/
        ├── collections/
        └── caches/
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional


# Storage mode type
StorageMode = Literal["global", "local"]


def get_global_root() -> Path:
    """Get the global storage root directory.
    
    Returns:
        Path to ~/.indexed
    """
    return Path.home() / ".indexed"


def get_local_root(workspace: Optional[Path] = None) -> Path:
    """Get the local storage root directory.
    
    Args:
        workspace: Optional workspace path. Defaults to current working directory.
        
    Returns:
        Path to ./.indexed relative to workspace
    """
    base = workspace or Path.cwd()
    return base / ".indexed"


def get_config_path(root: Path) -> Path:
    """Get the config file path for a given root.
    
    Args:
        root: Storage root directory (global or local)
        
    Returns:
        Path to config.toml within the root
    """
    return root / "config.toml"


def get_env_path(root: Path) -> Path:
    """Get the .env file path for a given root.
    
    Args:
        root: Storage root directory (global or local)
        
    Returns:
        Path to .env within the root
    """
    return root / ".env"


def get_data_root(root: Path) -> Path:
    """Get the data directory for a given root.
    
    Args:
        root: Storage root directory (global or local)
        
    Returns:
        Path to data/ within the root
    """
    return root / "data"


def get_collections_path(root: Path) -> Path:
    """Get the collections directory for a given root.
    
    Args:
        root: Storage root directory (global or local)
        
    Returns:
        Path to data/collections within the root
    """
    return get_data_root(root) / "collections"


def get_caches_path(root: Path) -> Path:
    """Get the caches directory for a given root.
    
    Args:
        root: Storage root directory (global or local)
        
    Returns:
        Path to data/caches within the root
    """
    return get_data_root(root) / "caches"


def has_local_storage(workspace: Optional[Path] = None) -> bool:
    """Check if local storage exists.
    
    Args:
        workspace: Optional workspace path. Defaults to current working directory.
        
    Returns:
        True if ./.indexed directory exists
    """
    return get_local_root(workspace).exists()


def has_global_storage() -> bool:
    """Check if global storage exists.
    
    Returns:
        True if ~/.indexed directory exists
    """
    return get_global_root().exists()


def has_local_config(workspace: Optional[Path] = None) -> bool:
    """Check if local config file exists.
    
    Args:
        workspace: Optional workspace path. Defaults to current working directory.
        
    Returns:
        True if ./.indexed/config.toml exists
    """
    return get_config_path(get_local_root(workspace)).exists()


def has_global_config() -> bool:
    """Check if global config file exists.
    
    Returns:
        True if ~/.indexed/config.toml exists
    """
    return get_config_path(get_global_root()).exists()


def ensure_storage_dirs(root: Path) -> None:
    """Ensure all storage directories exist.
    
    Creates the root directory and all subdirectories if they don't exist.
    
    Args:
        root: Storage root directory to initialize
    """
    root.mkdir(parents=True, exist_ok=True)
    get_data_root(root).mkdir(parents=True, exist_ok=True)
    get_collections_path(root).mkdir(parents=True, exist_ok=True)
    get_caches_path(root).mkdir(parents=True, exist_ok=True)


class StorageResolver:
    """Resolves storage paths based on mode, flags, and workspace preferences.
    
    This class provides a stateful way to resolve storage paths, taking into
    account CLI flags, workspace preferences, and config conflicts.
    
    Attributes:
        _workspace: The workspace directory (defaults to cwd)
        _mode_override: Explicit mode override from CLI flag
        _resolved_root: Cached resolved root path
    """
    
    def __init__(
        self,
        workspace: Optional[Path] = None,
        mode_override: Optional[StorageMode] = None,
    ) -> None:
        """Initialize the storage resolver.
        
        Args:
            workspace: Optional workspace path. Defaults to current working directory.
            mode_override: Explicit mode override ("global" or "local")
        """
        self._workspace = workspace or Path.cwd()
        self._mode_override = mode_override
        self._resolved_root: Optional[Path] = None
    
    @property
    def global_root(self) -> Path:
        """Get the global storage root."""
        return get_global_root()
    
    @property
    def local_root(self) -> Path:
        """Get the local storage root."""
        return get_local_root(self._workspace)
    
    @property
    def workspace(self) -> Path:
        """Get the workspace directory."""
        return self._workspace
    
    def resolve_root(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """Resolve the active storage root.
        
        Resolution order:
        1. CLI mode override (--local or --global flag)
        2. Workspace preference from config
        3. Default to global
        
        Args:
            workspace_preference: Preference for this workspace from config
            
        Returns:
            Resolved storage root path
        """
        # CLI flag takes precedence
        if self._mode_override == "local":
            return self.local_root
        if self._mode_override == "global":
            return self.global_root
        
        # Then workspace preference
        if workspace_preference == "local":
            return self.local_root
        if workspace_preference == "global":
            return self.global_root
        
        # Default to global
        return self.global_root
    
    def get_collections_path(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """Get resolved collections path."""
        root = self.resolve_root(workspace_preference)
        return get_collections_path(root)
    
    def get_caches_path(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """Get resolved caches path."""
        root = self.resolve_root(workspace_preference)
        return get_caches_path(root)
    
    def get_config_path(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """Get resolved config file path."""
        root = self.resolve_root(workspace_preference)
        return get_config_path(root)
    
    def get_env_path(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """Get resolved .env file path."""
        root = self.resolve_root(workspace_preference)
        return get_env_path(root)
    
    def has_conflict(self) -> bool:
        """Check if both local and global configs exist.
        
        Returns:
            True if both configs exist, indicating potential conflict
        """
        return has_local_config(self._workspace) and has_global_config()
    
    def ensure_dirs(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> None:
        """Ensure storage directories exist for resolved root."""
        root = self.resolve_root(workspace_preference)
        ensure_storage_dirs(root)


# Module-level singleton for convenience
_default_resolver: Optional[StorageResolver] = None


def get_resolver(
    workspace: Optional[Path] = None,
    mode_override: Optional[StorageMode] = None,
    reset: bool = False,
) -> StorageResolver:
    """Get or create the default storage resolver.
    
    Args:
        workspace: Optional workspace path
        mode_override: Optional mode override
        reset: If True, create a new resolver even if one exists
        
    Returns:
        StorageResolver instance
    """
    global _default_resolver
    
    if _default_resolver is None or reset:
        _default_resolver = StorageResolver(
            workspace=workspace,
            mode_override=mode_override,
        )
    
    return _default_resolver


def reset_resolver() -> None:
    """Reset the default resolver (useful for testing)."""
    global _default_resolver
    _default_resolver = None




