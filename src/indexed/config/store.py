from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

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

from .errors import SchemaVersionError
from .path_utils import deep_merge
from .storage import (
    get_global_root,
    get_config_path,
    get_env_path as storage_get_env_path,
)


CURRENT_SCHEMA_VERSION = "2"

# Keys the storage-mode collapse removed (workspace-profile/1, R1). A version-1
# file carrying any of them cannot be read as version 2, so it is rejected with
# a message naming what to delete rather than silently ignored.
REMOVED_WORKSPACE_KEYS = ("mode", "local_path", "global_path")


def env_to_mapping() -> Dict[str, Any]:
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


def enforce_schema_version(data: Mapping[str, Any], path: Path) -> str:
    """Validate a config/profile file's declared schema version (R7).

    ``"2"`` passes. ``"1"`` or absent passes only when the file carries none of
    the removed storage-mode keys; when it does, the error names them. Any
    other version is rejected — the bump is enforcement, not decoration.

    Parameters:
        data: The freshly-parsed TOML mapping (before any env overlay).
        path: The file the mapping came from, for the error message.

    Returns:
        The effective schema version, always ``CURRENT_SCHEMA_VERSION``.

    Raises:
        SchemaVersionError: On a removed key or an unrecognised version.
    """
    meta = data.get("_meta") or {}
    version = str(meta.get("schema_version", "1")) if isinstance(meta, Mapping) else "1"

    if version == CURRENT_SCHEMA_VERSION:
        return CURRENT_SCHEMA_VERSION

    if version != "1":
        raise SchemaVersionError(
            path,
            f"unrecognised schema_version {version!r} "
            f"(this build understands '1' and '{CURRENT_SCHEMA_VERSION}')",
        )

    workspace = data.get("workspace")
    offenders = (
        [f"[workspace].{k}" for k in REMOVED_WORKSPACE_KEYS if k in workspace]
        if isinstance(workspace, Mapping)
        else []
    )
    if offenders:
        raise SchemaVersionError(
            path,
            f"{', '.join(offenders)} {'was' if len(offenders) == 1 else 'were'} "
            "removed — local/global storage modes no longer exist. Delete "
            f"the key(s) and set [_meta] schema_version = "
            f'"{CURRENT_SCHEMA_VERSION}".',
        )

    # A clean version-1 file is read as version 2.
    return CURRENT_SCHEMA_VERSION


class TomlStore:
    """Read/write the one global config file (``~/.indexed/config.toml``).

    Runtime reads layer ``.env`` files and ``INDEXED__*`` env vars on top of it.
    The workspace overlay is NOT applied here — it travels as an immutable
    ``WorkspaceScope`` (see ``workspace.py``) so concurrent MCP requests for
    different workspaces cannot race through shared state.
    """

    def __init__(self, *, workspace: Optional[Path] = None) -> None:
        """Initialize the TomlStore.

        Args:
            workspace: Optional workspace path, used only to locate the
                workspace-level ``.env``. Defaults to the current working
                directory.
        """
        self.workspace = workspace or Path.cwd()

    @property
    def global_path(self) -> Path:
        """
        Get the path to the global configuration file (~/.indexed/config.toml).

        Returns:
            Path: Path to the global configuration file.
        """
        return get_config_path(get_global_root())

    @property
    def _global_env_path(self) -> Path:
        """Global .env file path (~/.indexed/.env)."""
        return storage_get_env_path(get_global_root())

    def get_env_path(self) -> str:
        """Return the .env file path secrets are written to, as a string."""
        return str(self._global_env_path)

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
            return tomllib.load(f)

    def read(self) -> Dict[str, Any]:
        """Read the global config, then overlay ``.env`` files and env vars.

        ``.env`` priority (highest first): real ``os.environ`` →
        ``~/.indexed/.env`` → ``<workspace>/.env`` (R1). Every load uses
        ``override=False``, so an earlier source always wins.

        Returns:
            Configuration dictionary with ``_schema_version`` attached.
        """
        data = self._read_toml_file(self.global_path)
        schema_version = enforce_schema_version(data, self.global_path)

        self._load_dotenv(self._global_env_path)
        self._load_cwd_dotenv()

        data = deep_merge(data, env_to_mapping())
        data.pop("_meta", None)
        data["_schema_version"] = schema_version
        return data

    def read_disk_only(self) -> Dict[str, Any]:
        """Read the global config.toml with NO env overlay.

        Unlike read(), this does not merge .env or INDEXED__* env vars — used
        as the persistence baseline for set()/delete() so an env-supplied value
        (e.g. a secret set only via INDEXED__*) is never round-tripped into
        config.toml by an unrelated write (C2).
        """
        data = self._read_toml_file(self.global_path)
        schema_version = enforce_schema_version(data, self.global_path)
        data.pop("_meta", None)
        data["_schema_version"] = schema_version
        return data

    def _load_cwd_dotenv(self) -> None:
        """Load ``<workspace>/.env`` with override=False (fills gaps only).

        ``interpolate=False`` (C4): `.env` here is secrets-only, never used
        for ``${VAR}`` composition, so disabling python-dotenv's default
        interpolation is the only way to stop a secret containing a literal
        ``${...}`` sequence from being silently mangled on load.
        """
        cwd_env = self.workspace / ".env"
        if cwd_env.exists():
            load_dotenv(str(cwd_env), override=False, interpolate=False)

    def has_global_config(self) -> bool:
        """
        Determine whether the global TOML configuration file exists.

        Returns:
            `True` if the global config file exists, `False` otherwise.
        """
        return self.global_path.exists()

    def _load_dotenv(self, env_path: Optional[Path] = None) -> None:
        """
        Load variables from a .env file into the process environment using python-dotenv.

        Uses python-dotenv for full .env file compatibility including multiline
        values, export prefixes, and escaped characters. Variable expansion
        (``${VAR}`` interpolation) is disabled (C4): `.env` here is
        secrets-only and never used for composition, so a secret containing a
        literal ``${...}`` sequence must survive unchanged rather than being
        silently mangled by python-dotenv's default interpolation.

        Parameters:
            env_path (Optional[Path]): Path to the .env file to load. If omitted, uses the global .env.
        """
        path = env_path or self._global_env_path
        if not path.exists():
            return

        # override=False preserves existing env vars; interpolate=False stops
        # `${...}` expansion from corrupting secrets (C4).
        load_dotenv(str(path), override=False, interpolate=False)

    def resolved_config_path(self) -> Path:
        """Return the config.toml path ``write()`` targets — always the global one.

        Lets a caller snapshot/restore the exact file a subsequent ``set()``/
        ``save_raw()`` will touch (foundation/6b review Finding 1).
        """
        return self.global_path

    def write(self, data: Mapping[str, Any]) -> None:
        """
        Write the given configuration mapping to the global TOML config file.

        Parameters:
            data (Mapping[str, Any]): Configuration data to persist.
        """
        write_toml_atomic(self.global_path, data)


def write_toml_atomic(target: Path, data: Mapping[str, Any]) -> None:
    """Serialize ``data`` and replace ``target`` atomically.

    B3: serialize BEFORE touching the target file, so an unserializable value
    (e.g. `None`) raises here and the existing file is never opened/truncated.
    Then write atomically (tmp -> fsync -> replace), mirroring the collections
    persister's tmp -> fsync -> os.replace pattern (disk_persister.py) instead
    of truncating in "w" mode. Shared by ``config.toml`` and the workspace
    profile so both get the same durability guarantee.
    """
    out = dict(data)
    out.pop("_schema_version", None)
    if "_meta" not in out:
        out["_meta"] = {"schema_version": CURRENT_SCHEMA_VERSION}

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
