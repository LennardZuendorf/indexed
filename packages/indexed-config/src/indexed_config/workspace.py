"""Workspace preference and storage path management."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .path_utils import get_by_path
from .storage import StorageMode, StorageResolver, has_local_config
from .store import TomlStore

# Workspace config section in config
WORKSPACE_PATH = "workspace"

# Default global path
DEFAULT_GLOBAL_PATH = "~/.indexed"


class WorkspaceManager:
    """Manages workspace preferences, storage paths, and conflict detection."""

    def __init__(
        self,
        store: TomlStore,
        resolver: StorageResolver,
        workspace: Path,
        mode_override: Optional[StorageMode] = None,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._workspace = workspace
        self._mode_override = mode_override

    def get_preference(self) -> Optional[StorageMode]:
        """Retrieve the storage mode preference for a workspace."""
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()

        workspace_config = get_by_path(raw, WORKSPACE_PATH, default={}) or {}
        mode = workspace_config.get("mode")

        if mode in ("global", "local"):
            return mode  # type: ignore[return-value]
        return None

    def set_preference(
        self,
        mode: StorageMode,
        workspace_path: Optional[Path] = None,
        global_path: Optional[str] = None,
    ) -> None:
        """Persist the workspace's storage preference into global config."""
        local_path = str(workspace_path or self._workspace)

        global_store = TomlStore(mode_override="global")
        raw = global_store.read()

        workspace_config: Dict[str, str] = {
            "mode": mode,
            "local_path": local_path,
        }

        if global_path and global_path != DEFAULT_GLOBAL_PATH:
            workspace_config["global_path"] = global_path

        raw[WORKSPACE_PATH] = workspace_config
        global_store.write(raw, to_global=True)

    def clear_preference(self) -> bool:
        """Clear any stored workspace preference from global config."""
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()

        if WORKSPACE_PATH in raw:
            del raw[WORKSPACE_PATH]
            global_store.write(raw, to_global=True)
            return True
        return False

    def get_config(self) -> Dict[str, str]:
        """Retrieve the effective workspace configuration."""
        raw = self._store.read()

        workspace_config = get_by_path(raw, WORKSPACE_PATH, default={}) or {}

        if workspace_config.get("mode") not in ("global", "local"):
            return {}

        return {
            "mode": workspace_config.get("mode", ""),
            "local_path": workspace_config.get("local_path", str(self._workspace)),
            "global_path": workspace_config.get("global_path", DEFAULT_GLOBAL_PATH),
        }

    def has_conflict(self) -> bool:
        """Check if both local and global configs exist with different values."""
        return self._store.configs_differ()

    def get_differences(self) -> Dict[str, tuple[Any, Any]]:
        """Get differences between local and global configs."""
        return self._store.get_config_differences()

    def resolve_storage_mode(self) -> StorageMode:
        """Determine the effective storage mode for the current workspace.

        Resolution order:
        1. CLI mode_override
        2. Workspace preference
        3. Auto-detect (local config exists → local)
        4. Default "global"
        """
        if self._mode_override:
            return self._mode_override

        pref = self.get_preference()
        if pref:
            return pref

        if has_local_config(self._workspace):
            return "local"

        return "global"

    def get_collections_path(self) -> Path:
        """Return the collections directory path for the resolved storage mode."""
        mode = self.resolve_storage_mode()
        return self._resolver.get_collections_path(mode)

    def get_caches_path(self) -> Path:
        """Return the caches directory path for the resolved storage mode."""
        mode = self.resolve_storage_mode()
        return self._resolver.get_caches_path(mode)

    def ensure_storage_dirs(self) -> None:
        """Ensure storage directories exist for the resolved storage mode."""
        pref = self.get_preference()
        self._resolver.ensure_dirs(pref)
