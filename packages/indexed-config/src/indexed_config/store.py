from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

# TOML read (tomllib on 3.11+, fallback to tomli)
if sys.version_info >= (3, 11):
    import tomllib  # type: ignore
else:
    try:
        import tomli as tomllib  # type: ignore
    except Exception:
        tomllib = None  # type: ignore

import tomlkit

from .path_utils import deep_merge
from .storage import (
    StorageMode,
    get_global_root,
    get_local_root,
    get_config_path,
    get_env_path as storage_get_env_path,
)


class TomlStore:
    """Read/write config with merge: Global, Workspace, ENV.

    - Global: ~/.indexed/config.toml (user's home directory)
    - Workspace: ./.indexed/config.toml (overrides global)
    - ENV overrides: INDEXED__section__key=value (overrides both)
    
    The global path has been changed from ~/.config/indexed/ to ~/.indexed/
    to provide a unified storage location for config, data, and caches.
    """

    def __init__(
        self,
        *,
        workspace: Optional[Path] = None,
        mode_override: Optional[StorageMode] = None,
    ) -> None:
        """Initialize the TomlStore.
        
        Args:
            workspace: Optional workspace path. Defaults to current working directory.
            mode_override: Optional storage mode override ("global" or "local").
                          If set, only that config source is used (no merging).
        """
        self.workspace = workspace or Path.cwd()
        self._mode_override = mode_override

    @property
    def global_root(self) -> Path:
        """
        Provide the path to the global storage root directory (~/.indexed).
        
        Returns:
            Path: Path to the global storage root directory.
        """
        return get_global_root()

    @property
    def global_path(self) -> Path:
        """
        Get the path to the global configuration file (~/.indexed/config.toml).
        
        Returns:
            Path: Path to the global configuration file.
        """
        return get_config_path(get_global_root())

    @property
    def local_root(self) -> Path:
        """Get the local storage root (./.indexed)."""
        return get_local_root(self.workspace)

    @property
    def workspace_path(self) -> Path:
        """
        Return the workspace/local configuration file path.
        
        Returns:
            Path to the workspace/local config file (./.indexed/config.toml).
        """
        return get_config_path(get_local_root(self.workspace))
    
    @property
    def env_path(self) -> Path:
        """
        Get the .env file path used for sensitive values.
        
        When the instance was created with mode_override == "global", returns the global .env path; otherwise returns the workspace/local .env path.
        
        Returns:
            Path: The filesystem path to the selected `.env` file.
        """
        if self._mode_override == "global":
            return storage_get_env_path(get_global_root())
        # Default to workspace .env for backward compatibility
        return storage_get_env_path(get_local_root(self.workspace))
    
    @property
    def global_env_path(self) -> Path:
        """
        Get the path to the global .env file under the global storage root.
        
        Returns:
            Path: Path to the global `.env` file (e.g., `~/.indexed/.env`).
        """
        return storage_get_env_path(get_global_root())
    
    @property
    def local_env_path(self) -> Path:
        """Path to the local .env file (./.indexed/.env)."""
        return storage_get_env_path(get_local_root(self.workspace))
    
    def get_env_path(self) -> str:
        """
        Return the resolved .env file path as a string.
        
        Returns:
            The path to the selected `.env` file (global or workspace) as a string.
        """
        return str(self.env_path)

    def _read_toml_file(self, path: Path) -> Dict[str, Any]:
        """
        Read and parse a TOML file at the given path and return its contents as a dictionary.
        
        If the file does not exist, returns an empty dictionary. Raises RuntimeError if a TOML parser
        (tomllib or tomli) is not available.
        
        Parameters:
            path (Path): Filesystem path to the TOML file.
        
        Returns:
            Dict[str, Any]: Parsed TOML data as a mapping; empty dict when the file is missing.
        
        Raises:
            RuntimeError: If no TOML parser (tomllib/tomli) is available for reading.
        """
        if not path.exists():
            return {}
        with open(path, "rb") as f:
            if tomllib is None:
                raise RuntimeError("tomllib/tomli not available for reading TOML")
            return tomllib.load(f)  # type: ignore

    def read(self) -> Dict[str, Any]:
        """Read and merge configuration from all sources.
        
        Merge order (later overrides earlier):
        1. Global config (~/.indexed/config.toml)
        2. Workspace/local config (./.indexed/config.toml) 
        3. Environment variables (INDEXED__section__key=value)
        
        If mode_override is set, only that config source is used (no merging
        between global and local, but env vars still apply).
        
        Returns:
            Merged configuration dictionary.
        """
        data: Dict[str, Any] = {}
        
        if self._mode_override == "local":
            # Only use local config
            data = self._read_toml_file(self.workspace_path)
            self._load_dotenv(self.local_env_path)
        elif self._mode_override == "global":
            # Only use global config
            data = self._read_toml_file(self.global_path)
            self._load_dotenv(self.global_env_path)
        else:
            # Normal merge: Global -> Workspace
            data = deep_merge(data, self._read_toml_file(self.global_path))
            data = deep_merge(data, self._read_toml_file(self.workspace_path))
            # Load both .env files (global first, then local overrides)
            self._load_dotenv(self.global_env_path)
            self._load_dotenv(self.local_env_path)
        
        # ENV vars always override
        env_data = self._env_to_mapping()
        data = deep_merge(data, env_data)
        return data
    
    def has_local_config(self) -> bool:
        """
        Determine whether the workspace (local) TOML configuration file exists.
        
        Returns:
            True if the workspace config file exists, False otherwise.
        """
        return self.workspace_path.exists()
    
    def has_global_config(self) -> bool:
        """
        Determine whether the global TOML configuration file exists.
        
        Returns:
            `True` if the global config file exists, `False` otherwise.
        """
        return self.global_path.exists()
    
    def configs_differ(self) -> bool:
        """
        Determine whether the workspace (local) and global TOML configurations contain differing values.
        
        Returns:
            `true` if both config files exist and at least one value differs; `false` otherwise.
        """
        if not self.has_local_config() or not self.has_global_config():
            return False
        
        local_data = self._read_toml_file(self.workspace_path)
        global_data = self._read_toml_file(self.global_path)
        
        return self._configs_have_differences(local_data, global_data)
    
    def _configs_have_differences(
        self,
        local: Dict[str, Any],
        global_: Dict[str, Any],
    ) -> bool:
        """
        Determine whether any keys present in both config mappings have different values, recursing into nested dicts.
        
        Parameters:
            local (Dict[str, Any]): Local configuration mapping; only keys present here are considered for conflict checks.
            global_ (Dict[str, Any]): Global configuration mapping to compare against.
        
        Returns:
            bool: `True` if a differing value is found for any key present in both mappings, `False` otherwise.
        """
        # Check keys in local
        for key, local_val in local.items():
            if key not in global_:
                continue  # Key only in local, not a conflict
            
            global_val = global_[key]
            
            if isinstance(local_val, dict) and isinstance(global_val, dict):
                if self._configs_have_differences(local_val, global_val):
                    return True
            elif local_val != global_val:
                return True
        
        return False
    
    def get_config_differences(self) -> Dict[str, tuple[Any, Any]]:
        """
        Produce a mapping of dot-separated paths to tuples containing the differing (local_value, global_value) for keys present in the workspace config.
        
        Returns:
            Dict[str, tuple[Any, Any]]: Mapping from dot-path (e.g., "section.subkey") to a tuple of (local_value, global_value). Returns an empty dict if either the local or global config is missing or if no differences exist.
        """
        if not self.has_local_config() or not self.has_global_config():
            return {}
        
        local_data = self._read_toml_file(self.workspace_path)
        global_data = self._read_toml_file(self.global_path)
        
        differences: Dict[str, tuple[Any, Any]] = {}
        self._collect_differences(local_data, global_data, "", differences)
        return differences
    
    def _collect_differences(
        self,
        local: Dict[str, Any],
        global_: Dict[str, Any],
        prefix: str,
        differences: Dict[str, tuple[Any, Any]],
    ) -> None:
        """
        Recursively record paths where values differ between a local and global configuration.
        
        Traverse keys present in `local` and, for any key also present in `global_`, record entries in `differences` when the corresponding values differ. Nested dictionaries are descended into; differences are recorded using dot-separated paths (e.g., "section.subkey") with the mapped value (local_value, global_value).
        
        Parameters:
            local (Dict[str, Any]): The local configuration subtree to inspect.
            global_ (Dict[str, Any]): The global configuration subtree to compare against.
            prefix (str): Dot-separated path prefix for the current recursion level; empty for the root.
            differences (Dict[str, tuple[Any, Any]]): Mutable mapping that will be populated with path -> (local_value, global_value) for each detected difference.
        """
        for key, local_val in local.items():
            path = f"{prefix}.{key}" if prefix else key
            
            if key not in global_:
                continue  # Only in local
            
            global_val = global_[key]
            
            if isinstance(local_val, dict) and isinstance(global_val, dict):
                self._collect_differences(local_val, global_val, path, differences)
            elif local_val != global_val:
                differences[path] = (local_val, global_val)
    
    def _load_dotenv(self, env_path: Optional[Path] = None) -> None:
        """
        Load variables from a .env file into the process environment if the file exists.
        
        Parameters:
            env_path (Optional[Path]): Path to the .env file to load. If omitted, uses the store's configured env_path.
        """
        path = env_path or self.env_path
        if not path.exists():
            return
        
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=value
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    # Only set if not already in environment (env takes precedence)
                    if key not in os.environ:
                        os.environ[key] = value

    def write(self, data: Mapping[str, Any], *, to_global: bool = False) -> None:
        """
        Write the given configuration mapping to the appropriate TOML config file (workspace or global).
        
        The destination is chosen as follows:
        - If `to_global` is True, write to the global config.
        - Else if the instance `mode_override` is "global", write to the global config.
        - Else if `mode_override` is "local", write to the workspace config.
        - Otherwise, write to the workspace config (backward-compatible default).
        
        Parameters:
            data (Mapping[str, Any]): Configuration data to persist.
            to_global (bool): If True, force writing to the global config; otherwise follow the mode override or default to the workspace.
        """
        if to_global:
            target = self.global_path
        elif self._mode_override == "global":
            target = self.global_path
        elif self._mode_override == "local":
            target = self.workspace_path
        else:
            # Default: write to workspace for backward compatibility
            target = self.workspace_path
        
        target.parent.mkdir(parents=True, exist_ok=True)
        # Preserve ordering but we just dump mapping
        with open(target, "w", encoding="utf-8") as f:
            tomlkit.dump(dict(data), f)
    
    def write_to_global(self, data: Mapping[str, Any]) -> None:
        """
        Write the provided configuration mapping to the global TOML config file.
        
        Parameters:
            data (Mapping[str, Any]): Configuration data to persist; must be representable as TOML.
        """
        self.write(data, to_global=True)

    def _env_to_mapping(self) -> Dict[str, Any]:
        """
        Convert environment variables with the `INDEXED__` prefix into a nested dictionary.
        
        Only variables whose names start with `INDEXED__` are considered. The portion after the prefix is split on `__` to form a nested path; empty segments are ignored and all key segments are lowercased. Values are kept as strings.
        
        Returns:
            mapping (Dict[str, Any]): Nested dictionary representing the matched environment variables, with lowercase keys and string values.
        """
        prefix = "INDEXED__"
        out: Dict[str, Any] = {}
        for k, v in os.environ.items():
            if not k.startswith(prefix):
                continue
            parts = [p for p in k[len(prefix):].split("__") if p]
            if not parts:
                continue
            cur = out
            for seg in parts[:-1]:
                seg = seg.lower()
                cur = cur.setdefault(seg, {})  # type: ignore[assignment]
            cur[parts[-1].lower()] = v
        return out