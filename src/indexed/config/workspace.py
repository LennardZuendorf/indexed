"""Workspace profile and per-invocation scope (workspace-profile/1, R2/R4).

The workspace profile is a small committable TOML file that does two things
only: it *filters* which global collections are active in a repo, and it
*overrides* some global settings for that repo. It deliberately does NOT live
in the ``ConfigService`` singleton — ``ConfigService`` serves the global base,
and ``WorkspaceScope`` is an immutable value resolved per CLI invocation or per
MCP request. Process-global mutable state would race between concurrent MCP
requests for different workspaces.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - project requires 3.11+
    try:
        import tomli as tomllib
    except Exception:
        tomllib = None

from .discovery import CANONICAL_NAME, LEGACY_RELPATH, find_profile
from .errors import WorkspaceResolutionError
from .path_utils import deep_merge, get_by_path
from .store import (
    CURRENT_SCHEMA_VERSION,
    enforce_schema_version,
    env_to_mapping,
    write_toml_atomic,
)

WORKSPACE_SECTION = "workspace"

#: Where a resolved workspace came from. ``"none"`` means no profile was found
#: — the view is unfiltered, and responses say so rather than implying it.
ScopeSource = Literal["argument", "header", "roots", "env", "cwd", "none"]

_SCAFFOLD = f'''\
# ./{CANONICAL_NAME} — workspace profile. Commit this file.
[_meta]
schema_version = "{CURRENT_SCHEMA_VERSION}"

# Collection filter — only these global collections are active here.
# Each <id> MUST match a collection directory name under
# ~/.indexed/data/collections/. `name` is a display label only.
#
# [workspace.collections.backend-docs]
# name = "Backend Docs"

# Settings override — global config changed for this workspace only.
#
# [workspace.overrides.core.v1.search]
# max_docs = 3
'''


class WorkspaceProfile:
    """Reader/writer for a workspace profile file.

    Reads are lazy and cached for the instance's lifetime; construct a fresh
    ``WorkspaceProfile`` to see another process's writes.
    """

    def __init__(self, path: Path, *, is_legacy: bool = False) -> None:
        self._path = path
        self._is_legacy = is_legacy
        self._data: Optional[Dict[str, Any]] = None

    @property
    def path(self) -> Path:
        """The profile file this instance reads and writes."""
        return self._path

    @property
    def is_legacy(self) -> bool:
        """True when this profile sits at the deprecated ``.indexed/config.toml``."""
        return self._is_legacy

    def _load(self) -> Dict[str, Any]:
        """Parse the profile, failing closed on a malformed or stale file."""
        if self._data is None:
            self._data = _read_toml(self._path)
            enforce_schema_version(self._data, self._path)
        return self._data

    def _collections(self) -> Dict[str, Any]:
        table = get_by_path(
            self._load(), f"{WORKSPACE_SECTION}.collections", default={}
        )
        return dict(table) if isinstance(table, dict) else {}

    def collection_ids(self) -> List[str]:
        """The declared collection ids — the workspace's allowlist."""
        return list(self._collections().keys())

    def collection_name(self, cid: str) -> Optional[str]:
        """The display label declared for ``cid``, if any."""
        entry = self._collections().get(cid)
        if not isinstance(entry, dict):
            return None
        name = entry.get("name")
        return name if isinstance(name, str) else None

    def overrides(self) -> Dict[str, Any]:
        """The workspace-wide setting overrides (``[workspace.overrides]``)."""
        table = get_by_path(self._load(), f"{WORKSPACE_SECTION}.overrides", default={})
        return dict(table) if isinstance(table, dict) else {}

    def collection_overrides(self, cid: str) -> Dict[str, Any]:
        """Overrides that apply only to ``cid``.

        Applied by the CLI/MCP layer when building that collection's search
        config; the engine services stay override-agnostic.
        """
        entry = self._collections().get(cid)
        if not isinstance(entry, dict):
            return {}
        table = entry.get("overrides")
        return dict(table) if isinstance(table, dict) else {}

    def add_collection(self, cid: str, name: Optional[str] = None) -> None:
        """Append (or relabel) a collection entry, atomically."""
        data = _read_toml(self._path)
        enforce_schema_version(data, self._path)
        workspace = data.setdefault(WORKSPACE_SECTION, {})
        collections = workspace.setdefault("collections", {})
        entry = collections.setdefault(cid, {})
        if name is not None:
            entry["name"] = name
        self._write(data)

    def drop_collection(self, cid: str) -> bool:
        """Remove a collection entry.

        Returns:
            True when an entry was removed, False when ``cid`` was not declared.
        """
        data = _read_toml(self._path)
        enforce_schema_version(data, self._path)
        collections = get_by_path(
            data, f"{WORKSPACE_SECTION}.collections", default=None
        )
        if not isinstance(collections, dict) or cid not in collections:
            return False
        del collections[cid]
        self._write(data)
        return True

    def _write(self, data: Dict[str, Any]) -> None:
        write_toml_atomic(self._path, data)
        self._data = None

    @staticmethod
    def scaffold(workspace: Path, *, force: bool = False) -> Path:
        """Create ``<workspace>/indexed.config.toml`` with a commented skeleton.

        Raises:
            FileExistsError: When the file already exists and ``force`` is False.
        """
        target = workspace / CANONICAL_NAME
        if target.exists() and not force:
            raise FileExistsError(f"{target} already exists (use force to overwrite)")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Same tmp -> fsync -> os.replace durability as write_toml_atomic; the
        # skeleton is written verbatim because a TOML round-trip would strip
        # the commented examples that make the file useful.
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(_SCAFFOLD)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return target


@dataclass(frozen=True)
class WorkspaceScope:
    """Immutable per-invocation / per-request resolution result."""

    workspace: Optional[Path] = None
    profile_path: Optional[Path] = None
    source: ScopeSource = "none"
    #: ``None`` means unfiltered; an empty list means nothing is visible.
    collection_ids: Optional[List[str]] = None
    overrides: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def apply(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Deep-merge ``overrides`` onto a config dict. Pure — no shared state.

        The profile sits BELOW ``INDEXED__*`` in the cascade (R4), so the env
        mapping is re-applied on top of the overlay: ``config`` already carries
        env values, and re-merging them is idempotent but restores their
        precedence over anything the profile just set.

        Neither ``config`` nor any global is mutated; the result is a new dict.
        """
        merged = deep_merge(config, self.overrides)
        return deep_merge(merged, env_to_mapping())


_scope_cache: Dict[Tuple[str, str, int, str], WorkspaceScope] = {}


def clear_scope_cache() -> None:
    """Drop every cached scope — used by tests and ``reload()``."""
    _scope_cache.clear()


def resolve_scope(
    workspace: Optional[Path] = None,
    *,
    source: Optional[ScopeSource] = None,
) -> WorkspaceScope:
    """Resolve the workspace profile in force for one invocation or request.

    Parameters:
        workspace: The workspace directory. ``None`` means the process cwd.
        source: Which resolution-chain step supplied ``workspace``. Defaults to
            ``"argument"`` when a workspace was passed and ``"cwd"`` otherwise.
            Reported as ``"none"`` whenever no profile is found, so an unfiltered
            view is stated rather than implied.

    Returns:
        An immutable ``WorkspaceScope``, cached by workspace + profile mtime.

    Raises:
        WorkspaceResolutionError: When an explicitly supplied workspace is not
            an existing directory, or a profile is found but unparseable.
        SchemaVersionError: When a found profile declares an unusable version.
    """
    resolved_source: ScopeSource = source or ("argument" if workspace else "cwd")

    if workspace is None:
        directory = Path.cwd().resolve()
    else:
        directory = workspace.expanduser().resolve()
        if not directory.is_dir():
            raise WorkspaceResolutionError(
                f"workspace {workspace} does not resolve to an existing directory"
            )

    found = find_profile(directory)
    if found is None:
        key = (str(directory), "", -1, resolved_source)
    else:
        profile_path, _is_legacy = found
        try:
            mtime = profile_path.stat().st_mtime_ns
        except OSError:  # pragma: no cover - raced deletion
            mtime = -1
        key = (str(directory), str(profile_path), mtime, resolved_source)

    cached = _scope_cache.get(key)
    if cached is not None:
        return cached

    scope = _build_scope(directory, found, resolved_source)
    _scope_cache[key] = scope
    return scope


def _build_scope(
    directory: Path,
    found: Optional[Tuple[Path, bool]],
    source: ScopeSource,
) -> WorkspaceScope:
    """Construct the scope for an already-located (or absent) profile."""
    if found is None:
        return WorkspaceScope(workspace=directory, source="none")

    profile_path, is_legacy = found
    warnings: List[str] = []
    if is_legacy:
        warnings.append(
            f"{profile_path} is a deprecated profile location; rename it to "
            f"{profile_path.parent / CANONICAL_NAME} ({CANONICAL_NAME})"
        )
    else:
        shadowed = profile_path.parent / LEGACY_RELPATH
        if shadowed.is_file():
            warnings.append(
                f"both {profile_path} and {shadowed} exist; using the canonical "
                f"{CANONICAL_NAME} and ignoring {shadowed}"
            )

    profile = WorkspaceProfile(profile_path, is_legacy=is_legacy)
    return WorkspaceScope(
        workspace=directory,
        profile_path=profile_path,
        source=source,
        collection_ids=profile.collection_ids(),
        overrides=profile.overrides(),
        warnings=warnings,
    )


def _read_toml(path: Path) -> Dict[str, Any]:
    """Parse a profile file, translating a parse failure into a closed failure."""
    if tomllib is None:  # pragma: no cover - project requires 3.11+
        raise RuntimeError("tomllib/tomli not available for reading TOML")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        raise WorkspaceResolutionError(
            f"workspace profile {path} could not be read: {exc}"
        ) from exc
