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
    has_local_config,
)


CURRENT_SCHEMA_VERSION = "1"


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
    def _global_root(self) -> Path:
        """Global storage root directory (~/.indexed)."""
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
    def _local_root(self) -> Path:
        """Local storage root (./.indexed)."""
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
    def _env_path(self) -> Path:
        """Resolved .env file path (global or workspace)."""
        if self._mode_override == "global":
            return storage_get_env_path(get_global_root())
        if self._mode_override == "local":
            return storage_get_env_path(get_local_root(self.workspace))
        # Auto-detect: local only if local config already exists
        if has_local_config(self.workspace):
            return storage_get_env_path(get_local_root(self.workspace))
        return storage_get_env_path(get_global_root())

    @property
    def _global_env_path(self) -> Path:
        """Global .env file path (~/.indexed/.env)."""
        return storage_get_env_path(get_global_root())

    @property
    def _local_env_path(self) -> Path:
        """Local .env file path (./.indexed/.env)."""
        return storage_get_env_path(get_local_root(self.workspace))

    def get_env_path(self) -> str:
        """Return the resolved .env file path as a string."""
        return str(self._env_path)

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
            self._load_dotenv(self._local_env_path)
        elif self._mode_override == "global":
            # Only use global config
            data = self._read_toml_file(self.global_path)
            self._load_dotenv(self._global_env_path)
        else:
            # Normal merge: Global -> Workspace
            data = deep_merge(data, self._read_toml_file(self.global_path))
            data = deep_merge(data, self._read_toml_file(self.workspace_path))
            # Load both .env files (global first, then local overrides)
            self._load_dotenv(self._global_env_path)
            self._load_dotenv(self._local_env_path)

        return self._apply_env_and_finalize(data)

    def read_for_mode(self, mode: StorageMode) -> Dict[str, Any]:
        """Read config for a specific resolved storage mode (no merging).

        Unlike read(), this reads ONE config.toml based on the resolved mode,
        and loads .env files in priority order:
        1. .indexed/.env from the resolved root (loaded first → gets set)
        2. CWD/.env (loaded second → only fills gaps via override=False)
        3. Real env vars already in os.environ are never overridden

        Args:
            mode: The resolved storage mode ("global" or "local").

        Returns:
            Configuration dictionary from the single resolved source.
        """
        if mode == "local":
            data = self._read_toml_file(self.workspace_path)
            self._load_dotenv(self._local_env_path)
        else:
            data = self._read_toml_file(self.global_path)
            self._load_dotenv(self._global_env_path)

        # Load CWD/.env (fills gaps only, never overrides)
        self._load_cwd_dotenv()

        return self._apply_env_and_finalize(data)

    def _apply_env_and_finalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply INDEXED__* env overrides and extract schema version."""
        env_data = self._env_to_mapping()
        data = deep_merge(data, env_data)

        schema_version = data.pop("_meta", {}).get("schema_version", "1")
        data["_schema_version"] = schema_version

        return data

    def _load_cwd_dotenv(self) -> None:
        """Load CWD/.env with override=False (fills gaps only)."""
        cwd_env = self.workspace / ".env"
        if cwd_env.exists():
            load_dotenv(str(cwd_env), override=False)

    def get_resolved_env_path(self, mode: StorageMode) -> str:
        """Return the .env file path for a specific resolved mode.

        This is used by EnvFileWriter to determine where to write
        sensitive values based on the resolved storage mode.

        Args:
            mode: The resolved storage mode ("global" or "local").

        Returns:
            String path to the .env file for the given mode.
        """
        if mode == "local":
            return str(self._local_env_path)
        return str(self._global_env_path)

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
        Load variables from a .env file into the process environment using python-dotenv.

        Uses python-dotenv for full .env file compatibility including multiline values, export prefixes, escaped characters, and variable expansion.

        Parameters:
            env_path (Optional[Path]): Path to the .env file to load. If omitted, uses the store's configured env_path.
        """
        path = env_path or self._env_path
        if not path.exists():
            return

        # Use python-dotenv with override=False to preserve existing env vars
        load_dotenv(str(path), override=False)

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
            # Default: follow auto-detection (same as StorageResolver.resolve_root)
            # Write to local only if a local config already exists; otherwise global
            if has_local_config(self.workspace):
                target = self.workspace_path
            else:
                target = self.global_path

        target.parent.mkdir(parents=True, exist_ok=True)

        # Build output dict, stripping internal marker and ensuring _meta
        out = dict(data)
        out.pop("_schema_version", None)
        if "_meta" not in out:
            out["_meta"] = {"schema_version": CURRENT_SCHEMA_VERSION}

        with open(target, "w", encoding="utf-8") as f:
            tomlkit.dump(out, f)

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
            parts = [p for p in k[len(prefix) :].split("__") if p]
            if not parts:
                continue
            cur = out
            for seg in parts[:-1]:
                seg = seg.lower()
                # Check for type conflict: if seg exists and is not a dict, raise error
                if seg in cur and not isinstance(cur[seg], dict):
                    raise ValueError(
                        f"Environment variable conflict: '{k}' conflicts with existing scalar value at '{seg}'. "
                        f"Cannot have both INDEXED__{seg.upper()}=value and INDEXED__{k[len(prefix) :]}"
                    )
                cur = cur.setdefault(seg, {})  # type: ignore[assignment]
            cur[parts[-1].lower()] = v
        return out
