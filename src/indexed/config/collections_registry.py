"""The global collection registry and per-workspace collection pointers.

Issue #346 (milestone #229). A collection's identity used to be its directory
name under one storage root, so two projects that wanted the same index had to
keep two copies. This module gives each collection that lives in the GLOBAL
store a stable id, and lets a workspace point at the shared copy instead of
owning one.

Three small JSON files, all written atomically (tmp -> fsync -> replace):

* ``<global>/data/registry.json`` — the registry proper: one record per
  collection in the global store, keyed by a stable id that never changes when
  a collection is renamed or re-registered.
* ``<workspace>/.indexed/collections.json`` — the pointer file: which registered
  collection ids this workspace uses, and the collections root to read them
  from. ``resolve_collections_context`` consults it, so CLI and MCP agree.
* ``<global>/data/registry-migration.json`` — the migration journal, owned by
  ``indexed.cli.storage`` (not this module); its path is defined here so both
  halves agree on one name.

Import rules: this is the ``config`` layer, so it may not import ``core``.
It is pure path/state bookkeeping — no collection is read or validated here.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional

from .errors import StorageError
from .storage import get_global_root

REGISTRY_VERSION = "1"
REGISTRY_FILENAME = "registry.json"
POINTER_FILENAME = "collections.json"
JOURNAL_FILENAME = "registry-migration.json"


class CollectionRegistryError(StorageError):
    """Raised when the collection registry cannot be read or trusted."""


def write_json_atomic(path: Path, payload: Any) -> None:
    """Write ``payload`` as JSON to ``path`` atomically.

    Same durability contract as ``TomlStore.write``: serialize first, write a
    sibling tmp file, fsync, then ``os.replace`` — a crash never leaves a
    half-written registry that would orphan the collections it describes.
    """
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, *, expected_version: str, what: str) -> Optional[dict]:
    """Read a versioned JSON file, or ``None`` when it does not exist yet.

    A file that exists but cannot be parsed, or whose ``version`` is not one we
    understand, raises: silently treating it as empty would drop stable ids and
    let a second copy of every collection be created (the exact bug this
    feature exists to prevent).
    """
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CollectionRegistryError(f"Cannot read {what} at '{path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise CollectionRegistryError(
            f"Malformed {what} at '{path}': expected a JSON object."
        )
    version = str(raw.get("version", ""))
    if version != expected_version:
        raise CollectionRegistryError(
            f"Unsupported {what} version {version!r} at '{path}' "
            f"(this indexed understands {expected_version!r})."
        )
    return raw


def utc_now() -> str:
    """Timestamp recorded in the registry/journal (UTC, second precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_collection_id() -> str:
    """A stable id for one collection; assigned once, never reused."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class CollectionRecord:
    """One collection that lives in the global store."""

    id: str
    name: str
    engine: str
    path: str
    workspace: str
    registered_at: str
    fingerprint: Optional[str] = None
    linked_workspaces: tuple[str, ...] = field(default_factory=tuple)

    def to_disk(self) -> dict:
        """Serialize with every key explicit (stable file diffs)."""
        return {
            "id": self.id,
            "name": self.name,
            "engine": self.engine,
            "path": self.path,
            "workspace": self.workspace,
            "registered_at": self.registered_at,
            "fingerprint": self.fingerprint,
            "linked_workspaces": list(self.linked_workspaces),
        }

    @classmethod
    def from_disk(cls, raw: dict) -> "CollectionRecord":
        """Rebuild a record, failing loud on the minimum identity fields."""
        for key in ("id", "name", "engine", "path", "workspace"):
            if key not in raw:
                raise CollectionRegistryError(
                    f"Registry entry is missing required key {key!r}: {raw!r}"
                )
        return cls(
            id=str(raw["id"]),
            name=str(raw["name"]),
            engine=str(raw["engine"]),
            path=str(raw["path"]),
            workspace=str(raw["workspace"]),
            registered_at=str(raw.get("registered_at", "")),
            fingerprint=(
                None if raw.get("fingerprint") is None else str(raw["fingerprint"])
            ),
            linked_workspaces=tuple(raw.get("linked_workspaces") or ()),
        )


class CollectionRegistry:
    """The registry of collections living in the global store.

    ``global_root`` defaults to ``~/.indexed`` resolved at call time (never at
    import time), so HOME isolation in tests moves it with everything else.
    """

    def __init__(self, global_root: Optional[Path] = None) -> None:
        self._global_root = global_root

    @property
    def global_root(self) -> Path:
        """The global storage root this registry belongs to."""
        return self._global_root or get_global_root()

    @property
    def path(self) -> Path:
        """Path of the registry file (``<global>/data/registry.json``)."""
        return self.global_root / "data" / REGISTRY_FILENAME

    @property
    def data_dir(self) -> Path:
        """``<global>/data`` — where the registry and journals live."""
        return self.global_root / "data"

    def journal_path_for(self, workspace_key: str) -> Path:
        """Journal for one workspace.

        Per workspace, not one global file: two projects migrate independently,
        and a completed journal must stay readable for that workspace's
        ``--rollback`` without blocking the next workspace's migration.
        """
        suffix = sha256(workspace_key.encode("utf-8")).hexdigest()[:8]
        stem = JOURNAL_FILENAME[: -len(".json")]
        return self.data_dir / f"{stem}-{suffix}.json"

    def _load(self) -> list[CollectionRecord]:
        raw = read_json(self.path, expected_version=REGISTRY_VERSION, what="registry")
        if raw is None:
            return []
        entries = raw.get("collections")
        if not isinstance(entries, list):
            raise CollectionRegistryError(
                f"Malformed registry at '{self.path}': 'collections' must be a list."
            )
        records = [CollectionRecord.from_disk(entry) for entry in entries]
        ids = [record.id for record in records]
        if len(set(ids)) != len(ids):
            raise CollectionRegistryError(
                f"Malformed registry at '{self.path}': duplicate collection ids."
            )
        return records

    def records(self) -> list[CollectionRecord]:
        """All registered collections, in file order."""
        return self._load()

    def find(self, name: str) -> Optional[CollectionRecord]:
        """The record for a collection name, or ``None``."""
        for record in self._load():
            if record.name == name:
                return record
        return None

    def by_id(self, collection_id: str) -> Optional[CollectionRecord]:
        """The record with this stable id, or ``None``."""
        for record in self._load():
            if record.id == collection_id:
                return record
        return None

    def add(
        self,
        *,
        name: str,
        engine: str,
        path: str,
        workspace: str,
        fingerprint: Optional[str] = None,
        record_id: Optional[str] = None,
    ) -> CollectionRecord:
        """Register a collection, or return the existing record for it.

        Idempotent on ``(name, path)``: a resumed migration or a repeated run
        must not mint a second id for the same collection. An existing record
        for the same NAME at a different path is a real collision — the caller
        must resolve it (rename) rather than silently retarget the id.
        """
        records = self._load()
        for record in records:
            if record.name == name:
                if record.path != path:
                    raise CollectionRegistryError(
                        f"Collection name '{name}' is already registered at "
                        f"'{record.path}' (id {record.id}); refusing to retarget it "
                        f"to '{path}'."
                    )
                return record
        record = CollectionRecord(
            id=record_id or new_collection_id(),
            name=name,
            engine=engine,
            path=path,
            workspace=workspace,
            registered_at=utc_now(),
            fingerprint=fingerprint,
        )
        records.append(record)
        self._save(records)
        return record

    def link_workspace(self, collection_id: str, workspace: str) -> CollectionRecord:
        """Record that ``workspace`` reuses this collection (idempotent)."""
        records = self._load()
        for index, record in enumerate(records):
            if record.id != collection_id:
                continue
            if workspace in record.linked_workspaces:
                return record
            updated = replace(
                record,
                linked_workspaces=tuple(sorted((*record.linked_workspaces, workspace))),
            )
            records[index] = updated
            self._save(records)
            return updated
        raise CollectionRegistryError(
            f"Cannot link workspace to unknown collection id {collection_id!r}."
        )

    def unlink_workspace(self, collection_id: str, workspace: str) -> None:
        """Drop a workspace link (idempotent)."""
        records = self._load()
        for index, record in enumerate(records):
            if record.id != collection_id or workspace not in record.linked_workspaces:
                continue
            remaining = tuple(w for w in record.linked_workspaces if w != workspace)
            records[index] = replace(record, linked_workspaces=remaining)
            self._save(records)
            return

    def remove(self, collection_id: str) -> bool:
        """Remove one record; ``True`` when it existed."""
        records = self._load()
        remaining = [record for record in records if record.id != collection_id]
        if len(remaining) == len(records):
            return False
        if remaining:
            self._save(remaining)
        else:
            self.path.unlink(missing_ok=True)
        return True

    def _save(self, records: list[CollectionRecord]) -> None:
        write_json_atomic(
            self.path,
            {
                "version": REGISTRY_VERSION,
                "collections": [record.to_disk() for record in records],
            },
        )


class WorkspacePointers:
    """The per-workspace pointer file (``./.indexed/collections.json``).

    It says which registered collections this workspace uses and where the
    collection bytes live. ``resolve_collections_context`` reads it, so a
    workspace can reuse a collection that physically lives in the global store.
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)

    @property
    def path(self) -> Path:
        """Path of the pointer file inside the workspace."""
        return self.workspace / ".indexed" / POINTER_FILENAME

    def read(self) -> dict:
        """Raw pointer payload (``{}`` when the workspace has none)."""
        raw = read_json(
            self.path, expected_version=REGISTRY_VERSION, what="workspace pointers"
        )
        return raw or {}

    def shared_root(self) -> Optional[Path]:
        """The collections root this workspace points at, if it is usable.

        Returns ``None`` when there is no pointer, no recorded root, or the
        recorded root has since disappeared — callers then fall back to the
        workspace's own storage rather than failing a search outright.
        """
        root = self.read().get("collections_root")
        if not root:
            return None
        candidate = Path(str(root))
        return candidate if candidate.is_dir() else None

    def resolve(self, name: str) -> Optional[str]:
        """The collection id this workspace uses for ``name``, or ``None``."""
        collections = self.read().get("collections") or {}
        value = collections.get(name) if isinstance(collections, dict) else None
        return None if value is None else str(value)

    def link(self, name: str, collection_id: str, collections_root: Path) -> None:
        """Point ``name`` at ``collection_id`` living under ``collections_root``."""
        raw = self.read()
        collections = dict(raw.get("collections") or {})
        collections[name] = collection_id
        write_json_atomic(
            self.path,
            {
                "version": REGISTRY_VERSION,
                "collections_root": str(collections_root),
                "collections": collections,
            },
        )

    def unlink(self, name: str) -> None:
        """Drop ``name`` from the pointer file, removing the file when empty."""
        raw = self.read()
        collections = dict(raw.get("collections") or {})
        if collections.pop(name, None) is None:
            return
        if not collections:
            self.path.unlink(missing_ok=True)
            return
        write_json_atomic(
            self.path,
            {
                "version": REGISTRY_VERSION,
                "collections_root": raw.get("collections_root"),
                "collections": collections,
            },
        )

    def workspace_key(self) -> str:
        """Stable absolute path used to identify this workspace in records."""
        return str(self.workspace.resolve())
