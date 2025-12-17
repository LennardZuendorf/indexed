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
    """
    Return the path to the config.toml file inside the provided storage root.
    
    Parameters:
        root (Path): Storage root directory (e.g., global or local)
    
    Returns:
        Path: Path to the config.toml file within the root
    """
    return root / "config.toml"


def get_env_path(root: Path) -> Path:
    """
    Return the path to the .env file inside the given storage root.
    
    Parameters:
        root (Path): Storage root directory (global or local).
    
    Returns:
        Path: Path to the `.env` file within `root`.
    """
    return root / ".env"


def get_data_root(root: Path) -> Path:
    """
    Resolve the path to the data directory inside a storage root.
    
    Parameters:
        root (Path): Storage root directory (global or local).
    
    Returns:
        Path: Path to the `data` directory within the given root.
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
    """
    Determine whether a local .indexed storage root exists for the given workspace.
    
    Parameters:
        workspace (Optional[Path]): Workspace directory to check. If None, the current working directory is used.
    
    Returns:
        True if the .indexed directory exists at the workspace, False otherwise.
    """
    return get_local_root(workspace).exists()


def has_global_storage() -> bool:
    """
    Determine whether the global storage root (~/.indexed) exists.
    
    Returns:
        True if the global storage root (~/.indexed) exists, False otherwise.
    """
    return get_global_root().exists()


def has_local_config(workspace: Optional[Path] = None) -> bool:
    """
    Determine whether the local workspace config file exists.
    
    Parameters:
        workspace (Optional[Path]): Workspace directory; defaults to the current working directory.
    
    Returns:
        `true` if the file `.indexed/config.toml` exists in the workspace directory, `false` otherwise.
    """
    return get_config_path(get_local_root(workspace)).exists()


def has_global_config() -> bool:
    """
    Determine whether the global config file (~/.indexed/config.toml) exists.
    
    Returns:
        `true` if the global config file exists at ~/.indexed/config.toml, `false` otherwise.
    """
    return get_config_path(get_global_root()).exists()


def ensure_storage_dirs(root: Path) -> None:
    """
    Create the storage root and its data, collections, and caches subdirectories if they do not exist.
    
    Parameters:
        root (Path): Root directory under which `data`, `data/collections`, and `data/caches` will be created.
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
        """
        Create a StorageResolver bound to a workspace and optional mode override.
        
        Parameters:
            workspace (Optional[Path]): Workspace directory; defaults to the current working directory.
            mode_override (Optional[StorageMode]): Explicit storage mode to force ("global" or "local"); when provided it takes precedence over workspace preference.
        """
        self._workspace = workspace or Path.cwd()
        self._mode_override = mode_override
        self._resolved_root: Optional[Path] = None
    
    @property
    def global_root(self) -> Path:
        """
        Access the global storage root path (~/.indexed).
        
        Returns:
            global_root (Path): Path to the global storage root directory.
        """
        return get_global_root()
    
    @property
    def local_root(self) -> Path:
        """
        Resolve the local storage root path for the resolver's workspace.
        
        Returns:
            Path: Path to the local storage root (./.indexed) for the resolver's workspace.
        """
        return get_local_root(self._workspace)
    
    @property
    def workspace(self) -> Path:
        """
        Return the workspace directory used by the resolver.
        
        Returns:
            Path: The resolved workspace directory path.
        """
        return self._workspace
    
    def resolve_root(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """
        Resolve which storage root should be used for operations.
        
        Resolution order:
        1. CLI mode override (`self._mode_override`)
        2. `workspace_preference` passed from workspace config
        3. Default to the global root
        
        Parameters:
            workspace_preference (Optional[StorageMode]): Workspace-configured preference, either `"local"` or `"global"`; omitted or None means no preference.
        
        Returns:
            Path: The resolved storage root path.
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
        """
        Resolve the active storage root (using CLI override, workspace preference, or default) and return its collections directory path.
        
        Parameters:
            workspace_preference (Optional[StorageMode]): Optional preference for storage mode ("local" or "global") used during resolution; if omitted the resolver's stored preference or defaults are used.
        
        Returns:
            Path: Path to the `data/collections` directory within the resolved storage root.
        """
        root = self.resolve_root(workspace_preference)
        return get_collections_path(root)
    
    def get_caches_path(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """
        Resolve the active storage root and return the path to its caches directory.
        
        Parameters:
            workspace_preference (Optional[StorageMode]): Optional preference for storage mode (e.g., "local" or "global") used when resolving which root to use.
        
        Returns:
            Path: Path to the `data/caches` directory under the resolved storage root.
        """
        root = self.resolve_root(workspace_preference)
        return get_caches_path(root)
    
    def get_config_path(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """
        Resolve the active storage root and return the path to its config file.
        
        Parameters:
            workspace_preference (Optional[StorageMode]): Optional preference for 'local' or 'global' storage used when resolving the root; if omitted, the resolver's CLI override, cached resolution, or default rules apply.
        
        Returns:
            Path: Path to the `config.toml` file within the resolved storage root.
        """
        root = self.resolve_root(workspace_preference)
        return get_config_path(root)
    
    def get_env_path(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> Path:
        """
        Resolve the active storage root and return the path to its `.env` file.
        
        Parameters:
            workspace_preference (Optional[StorageMode]): Optional preference to choose local or global storage when resolving the root; if omitted, the resolver's current configuration is used.
        
        Returns:
            Path: Path to the `.env` file inside the resolved storage root.
        """
        root = self.resolve_root(workspace_preference)
        return get_env_path(root)
    
    def has_conflict(self) -> bool:
        """
        Determine whether both the local and global config files exist.
        
        Returns:
            bool: True if both local and global config files exist, False otherwise.
        """
        return has_local_config(self._workspace) and has_global_config()
    
    def ensure_dirs(
        self,
        workspace_preference: Optional[StorageMode] = None,
    ) -> None:
        """
        Ensure storage directories exist for the resolved storage root.
        
        Resolve the active storage root (using the resolver's configuration and the optional
        workspace_preference) and create the root directory and its required subdirectories
        (e.g., data, data/collections, data/caches) if they do not already exist.
        
        Parameters:
            workspace_preference (Optional[StorageMode]): Preferred storage mode to use when
                resolving the root; when omitted the resolver's configured preference is used.
        """
        root = self.resolve_root(workspace_preference)
        ensure_storage_dirs(root)


# Module-level singleton for convenience
_default_resolver: Optional[StorageResolver] = None


def get_resolver(
    workspace: Optional[Path] = None,
    mode_override: Optional[StorageMode] = None,
    reset: bool = False,
) -> StorageResolver:
    """
    Get the singleton StorageResolver, creating a new instance when none exists or when reset is True.
    
    Parameters:
        workspace (Optional[Path]): Workspace directory used by the resolver; defaults to the current working directory when None.
        mode_override (Optional[StorageMode]): Explicit storage mode to force ("global" or "local"); if None the resolver will use workspace preferences or defaults.
        reset (bool): If True, create and return a new resolver even if a default already exists.
    
    Returns:
        StorageResolver: The active resolver instance.
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


