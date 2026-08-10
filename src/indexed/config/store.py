from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# TOML read (tomllib on 3.11+, fallback to tomli)
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except Exception:
        tomllib = None

import tomlkit
from dotenv import load_dotenv

from .path_utils import deep_merge, get_by_path
from .storage import (
    StorageMode,
    get_config_path,
    get_global_root,
    get_local_root,
    resolve_storage_mode,
)
from .storage import (
    get_env_path as storage_get_env_path,
)

CURRENT_SCHEMA_VERSION = "1"


class TomlStore:
    """Read/write config for a single resolved storage mode.

    Runtime reads use read_for_mode(mode) — one config.toml (global OR local),
    then .env overlay and INDEXED__* env vars.
    """

    def __init__(
        self,
        *,
        workspace: Path | None = None,
        mode_override: StorageMode | None = None,
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
        """Resolved .env file path (global or workspace).

        No workspace preference here (TomlStore only sees the CLI override and the
        local-config auto-detect), so ``workspace_preference`` is left None.
        """
        mode = resolve_storage_mode(
            mode_override=self._mode_override,
            workspace_preference=None,
            workspace=self.workspace,
        )
        root = get_local_root(self.workspace) if mode == "local" else get_global_root()
        return storage_get_env_path(root)

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

    def _read_toml_file(self, path: Path) -> dict[str, Any]:
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
            return tomllib.load(f)

    def read_for_mode(self, mode: StorageMode) -> dict[str, Any]:
        """Read config for a specific resolved storage mode (no merging).

        Reads ONE config.toml based on the resolved mode,
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

    def read_disk_only_for_mode(self, mode: StorageMode) -> dict[str, Any]:
        """Read config.toml for a resolved storage mode, with NO env overlay.

        Unlike read_for_mode(), this does not merge .env or INDEXED__* env
        vars — used as the persistence baseline for set()/delete() so an
        env-supplied value (e.g. a secret set only via INDEXED__*) is never
        round-tripped into config.toml by an unrelated write (C2).

        Args:
            mode: The resolved storage mode ("global" or "local").

        Returns:
            Configuration dictionary read from disk only.
        """
        path = self.workspace_path if mode == "local" else self.global_path
        data = self._read_toml_file(path)
        schema_version = data.pop("_meta", {}).get("schema_version", "1")
        data["_schema_version"] = schema_version
        return data

    def _apply_env_and_finalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Apply INDEXED__* env overrides and extract schema version."""
        env_data = self._env_to_mapping()
        data = deep_merge(data, env_data)

        schema_version = data.pop("_meta", {}).get("schema_version", "1")
        data["_schema_version"] = schema_version

        return data

    def _load_cwd_dotenv(self) -> None:
        """Load CWD/.env with override=False (fills gaps only).

        ``interpolate=False`` (C4): `.env` here is secrets-only, never used
        for ``${VAR}`` composition, so disabling python-dotenv's default
        interpolation is the only way to stop a secret containing a literal
        ``${...}`` sequence from being silently mangled on load.
        """
        cwd_env = self.workspace / ".env"
        if cwd_env.exists():
            load_dotenv(str(cwd_env), override=False, interpolate=False)

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
        local: dict[str, Any],
        global_: dict[str, Any],
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

    def get_config_differences(self) -> dict[str, tuple[Any, Any]]:
        """
        Produce a mapping of dot-separated paths to tuples containing the differing (local_value, global_value) for keys present in the workspace config.

        Returns:
            Dict[str, tuple[Any, Any]]: Mapping from dot-path (e.g., "section.subkey") to a tuple of (local_value, global_value). Returns an empty dict if either the local or global config is missing or if no differences exist.
        """
        if not self.has_local_config() or not self.has_global_config():
            return {}

        local_data = self._read_toml_file(self.workspace_path)
        global_data = self._read_toml_file(self.global_path)

        differences: dict[str, tuple[Any, Any]] = {}
        self._collect_differences(local_data, global_data, "", differences)
        return differences

    def _collect_differences(
        self,
        local: dict[str, Any],
        global_: dict[str, Any],
        prefix: str,
        differences: dict[str, tuple[Any, Any]],
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

    def _load_dotenv(self, env_path: Path | None = None) -> None:
        """
        Load variables from a .env file into the process environment using python-dotenv.

        Uses python-dotenv for full .env file compatibility including multiline
        values, export prefixes, and escaped characters. Variable expansion
        (``${VAR}`` interpolation) is disabled (C4): `.env` here is
        secrets-only and never used for composition, so a secret containing a
        literal ``${...}`` sequence must survive unchanged rather than being
        silently mangled by python-dotenv's default interpolation.

        Parameters:
            env_path (Optional[Path]): Path to the .env file to load. If omitted, uses the store's configured env_path.
        """
        path = env_path or self._env_path
        if not path.exists():
            return

        # override=False preserves existing env vars; interpolate=False stops
        # `${...}` expansion from corrupting secrets (C4).
        load_dotenv(str(path), override=False, interpolate=False)

    def _get_workspace_preference(self) -> StorageMode | None:
        """Read the stored ``[workspace] mode`` preference from the global config.

        Duplicates ``WorkspaceManager.get_preference()`` rather than importing
        it: ``workspace.py`` imports ``TomlStore``, so the reverse import
        would be circular. Kept in lockstep with that method so the write-side
        resolution below can never diverge from the read-side resolution
        (``WorkspaceManager.resolve_storage_mode()``) that ``ConfigService``
        uses for its baseline read (R1).
        """
        global_store = TomlStore(mode_override="global")
        raw = global_store.read_for_mode("global")
        workspace_config = get_by_path(raw, "workspace", default={}) or {}
        mode = workspace_config.get("mode")
        if mode in ("global", "local"):
            return mode  # type: ignore[return-value]
        return None

    def _resolve_write_target(
        self, *, to_global: bool = False, mode: StorageMode | None = None
    ) -> Path:
        """
        Determine which config.toml ``write()`` would target right now, without writing.

        The destination is chosen as follows:
        - If `to_global` is True, the global config.
        - Else if `mode` is given, that exact resolved mode is used as-is
          (lets a caller that already resolved its own mode — e.g.
          ``ConfigService.set()``/``delete()`` — guarantee this matches the
          mode it used for the corresponding baseline read).
        - Else if the instance `mode_override` is "global", the global config.
        - Else if `mode_override` is "local", the workspace config.
        - Else if a workspace storage-mode preference is stored, that mode.
        - Otherwise, the workspace config if it already exists, else the
          global config (same auto-detection as StorageResolver.resolve_root).

        Parameters:
            to_global (bool): If True, force the global config; otherwise follow the mode override or auto-detect.
            mode (Optional[StorageMode]): An already-resolved mode to use verbatim, bypassing the cascade below.

        Returns:
            Path: The config.toml path ``write()`` would target for this input.
        """
        if to_global:
            return self.global_path
        if mode is None:
            # Follow the shared cascade (same as WorkspaceManager.resolve_storage_mode):
            # override → workspace preference → local-config-present → global.
            mode = resolve_storage_mode(
                mode_override=self._mode_override,
                workspace_preference=(
                    None if self._mode_override else self._get_workspace_preference()
                ),
                workspace=self.workspace,
            )
        return self.workspace_path if mode == "local" else self.global_path

    def resolved_config_path(self, *, mode: StorageMode | None = None) -> Path:
        """Return the config.toml path a plain ``write()`` would target right now.

        Lets a caller snapshot/restore the exact file a subsequent ``set()``/
        ``save_raw()`` will touch (foundation/6b review Finding 1) without
        duplicating ``write()``'s target-selection logic.

        Parameters:
            mode (Optional[StorageMode]): An already-resolved mode to use verbatim (see ``_resolve_write_target``).
        """
        return self._resolve_write_target(mode=mode)

    def write(
        self,
        data: Mapping[str, Any],
        *,
        to_global: bool = False,
        mode: StorageMode | None = None,
    ) -> None:
        """
        Write the given configuration mapping to the appropriate TOML config file (workspace or global).

        The destination is chosen as described in ``_resolve_write_target()``.

        Parameters:
            data (Mapping[str, Any]): Configuration data to persist.
            to_global (bool): If True, force writing to the global config; otherwise follow the mode override or default to the workspace.
            mode (Optional[StorageMode]): An already-resolved mode to use verbatim (see ``_resolve_write_target``).
        """
        target = self._resolve_write_target(to_global=to_global, mode=mode)

        # Build output dict, stripping internal marker and ensuring _meta
        out = dict(data)
        out.pop("_schema_version", None)
        if "_meta" not in out:
            out["_meta"] = {"schema_version": CURRENT_SCHEMA_VERSION}

        # B3: serialize BEFORE touching the target file, so an unserializable
        # value (e.g. `None`) raises here and the existing file is never
        # opened/truncated. Then write atomically (tmp -> fsync -> replace),
        # mirroring the collections persister's tmp -> fsync -> os.replace
        # pattern (disk_persister.py) instead of truncating in "w" mode.
        serialized = tomlkit.dumps(out)

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(serialized)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def write_to_global(self, data: Mapping[str, Any]) -> None:
        """
        Write the provided configuration mapping to the global TOML config file.

        Parameters:
            data (Mapping[str, Any]): Configuration data to persist; must be representable as TOML.
        """
        self.write(data, to_global=True)

    def _env_to_mapping(self) -> dict[str, Any]:
        """
        Convert environment variables with the `INDEXED__` prefix into a nested dictionary.

        Only variables whose names start with `INDEXED__` are considered. The portion after the prefix is split on `__` to form a nested path; empty segments are ignored and all key segments are lowercased. Values are kept as strings.

        Raises:
            ValueError: If a variable's final path segment collides with an
                existing nested dict built by another (order-earlier)
                variable — e.g. ``INDEXED__A__B`` followed by ``INDEXED__A``
                — which would otherwise silently drop the nested subtree
                (R15). Mirrors the same guard already applied to intermediate
                path segments below.

        Returns:
            mapping (Dict[str, Any]): Nested dictionary representing the matched environment variables, with lowercase keys and string values.
        """
        prefix = "INDEXED__"
        out: dict[str, Any] = {}
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
            last = parts[-1].lower()
            # Guard the final assignment the same way: a scalar must not
            # silently clobber a nested dict built by an earlier variable.
            if last in cur and isinstance(cur[last], dict):
                raise ValueError(
                    f"Environment variable conflict: '{k}' would overwrite the "
                    f"nested value at '{last}' with a scalar. Cannot have both "
                    f"INDEXED__{k[len(prefix) :]} and a nested "
                    f"INDEXED__{k[len(prefix) :]}__* variable."
                )
            cur[last] = v
        return out
