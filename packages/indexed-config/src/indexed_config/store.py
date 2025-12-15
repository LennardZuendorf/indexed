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
from dotenv import load_dotenv

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
        """Get the global storage root (~/.indexed)."""
        return get_global_root()

    @property
    def global_path(self) -> Path:
        """Get the global config file path (~/.indexed/config.toml)."""
        return get_config_path(get_global_root())

    @property
    def local_root(self) -> Path:
        """Get the local storage root (./.indexed)."""
        return get_local_root(self.workspace)

    @property
    def workspace_path(self) -> Path:
        """Get the workspace/local config file path (./.indexed/config.toml)."""
        return get_config_path(get_local_root(self.workspace))
    
    @property
    def env_path(self) -> Path:
        """Path to the .env file for sensitive values.
        
        Returns the .env path based on mode_override if set,
        otherwise defaults to the workspace .env.
        """
        if self._mode_override == "global":
            return storage_get_env_path(get_global_root())
        # Default to workspace .env for backward compatibility
        return storage_get_env_path(get_local_root(self.workspace))
    
    @property
    def global_env_path(self) -> Path:
        """Path to the global .env file (~/.indexed/.env)."""
        return storage_get_env_path(get_global_root())
    
    @property
    def local_env_path(self) -> Path:
        """Path to the local .env file (./.indexed/.env)."""
        return storage_get_env_path(get_local_root(self.workspace))
    
    def get_env_path(self) -> str:
        """Get the .env file path as string."""
        return str(self.env_path)

    def _read_toml_file(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        if tomllib is None:
            raise RuntimeError("tomllib/tomli not available for reading TOML")
        with open(path, "rb") as f:
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
        """Check if local/workspace config exists."""
        return self.workspace_path.exists()
    
    def has_global_config(self) -> bool:
        """Check if global config exists."""
        return self.global_path.exists()
    
    def configs_differ(self) -> bool:
        """Check if local and global configs have different values.
        
        Returns:
            True if both configs exist and have differing values,
            False if only one exists or they are identical.
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
        """Recursively check if two config dicts have differences.
        
        Only checks keys that exist in both configs - we're looking for
        conflicts, not missing keys.
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
        """Get a dict of differing values between local and global configs.
        
        Returns:
            Dict mapping dot-paths to (local_value, global_value) tuples.
            Empty dict if no differences or only one config exists.
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
        """Recursively collect differing values."""
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
        """Load .env file into environment using python-dotenv.
        
        Uses python-dotenv for full .env file compatibility including
        multiline values, export prefixes, escaped characters, and
        variable expansion.
        
        Args:
            env_path: Path to the .env file. Defaults to self.env_path.
        """
        path = env_path or self.env_path
        if not path.exists():
            return
        
        # Use python-dotenv with override=False to preserve existing env vars
        load_dotenv(str(path), override=False)

    def write(self, data: Mapping[str, Any], *, to_global: bool = False) -> None:
        """Write configuration to TOML file.
        
        Args:
            data: Configuration data to write.
            to_global: If True, write to global config. If False, write to
                      workspace config (default) unless mode_override is set.
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
        """Write configuration to global config file."""
        self.write(data, to_global=True)

    def _env_to_mapping(self) -> Dict[str, Any]:
        """Convert INDEXED__A__B=val env vars to nested dict {"a": {"b": val}}.
        Values are left as strings; Pydantic will coerce types on bind().
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
                # Check for type conflict: if seg exists and is not a dict, raise error
                if seg in cur and not isinstance(cur[seg], dict):
                    raise ValueError(
                        f"Environment variable conflict: '{k}' conflicts with existing scalar value at '{seg}'. "
                        f"Cannot have both INDEXED__{seg.upper()}=value and INDEXED__{k[len(prefix):]}"
                    )
                cur = cur.setdefault(seg, {})  # type: ignore[assignment]
            cur[parts[-1].lower()] = v
        return out
