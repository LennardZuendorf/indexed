"""``indexed.toml`` — the committed workspace definition (#344).

A workspace definition *selects* collections that already live in the global
store. It is never a store: it carries no collection data, no absolute paths and
no credentials, so it can be committed and two clones of the same repository
resolve the same selection.

Discovery walks up from the workspace to the nearest ``indexed.toml``, stopping
before ``$HOME`` — a definition belongs to a repository, not to the user's home
directory. No file found means *no selection*, which is the pre-#344 behaviour:
every collection in the resolved store is in scope.

This is the ``config`` layer: it may import the registry but never ``core`` or
``cli``.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .collections_registry import CollectionRegistry
from .errors import StorageError

#: The committed definition's file name, at the Git worktree root.
SELECTION_FILENAME = "indexed.toml"

#: Format version. A definition without one cannot be migrated later, so it is
#: required rather than defaulted.
SELECTION_VERSION = 1

#: A stable collection id (``uuid4().hex``). The canonical entry form; anything
#: else in ``use`` is read as a collection name so the file stays hand-editable.
_STABLE_ID = re.compile(r"^[0-9a-f]{32}$")

_MANIFEST = "manifest.json"

_HEADER = """\
# indexed.toml — commit this file.
#
# It selects collections that already live in the global store
# (~/.indexed/data). It never contains collection data, paths or credentials.
"""


class WorkspaceSelectionError(StorageError):
    """The workspace definition is unreadable, unsupported or unresolvable."""


@dataclass(frozen=True)
class SelectedCollection:
    """One collection the workspace selects, resolved against the store."""

    name: str
    id: Optional[str] = None
    #: Position in ``[collections].use`` — kept so a resolved entry and an
    #: unresolved one can be put back into the order the user wrote (#340).
    position: int = 0


@dataclass(frozen=True)
class UnresolvedEntry:
    """A definition entry the store can no longer serve.

    Data, not an exception, because a *search* degrades per source: it reports
    this entry as a `missing` source and answers from the rest (#340 R4).
    Every other command resolves strictly and turns it back into the same
    ``WorkspaceSelectionError`` it has always raised.
    """

    entry: str
    name: str
    reason: str
    position: int = 0


@dataclass(frozen=True)
class WorkspaceSelection:
    """A resolved ``indexed.toml``: where it is and what it selects."""

    path: Path
    root: Path
    collections: tuple[SelectedCollection, ...]
    #: Entries that no longer resolve (strict resolution raises instead).
    unresolved: tuple[UnresolvedEntry, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        """The selected collection names that resolved, in definition order."""
        return tuple(collection.name for collection in self.collections)

    @property
    def scope(self) -> tuple[str, ...]:
        """Every intended name, resolved or not, in definition order."""
        ordered = [(entry.position, entry.name) for entry in self.collections]
        ordered += [(entry.position, entry.name) for entry in self.unresolved]
        return tuple(name for _position, name in sorted(ordered))

    def __contains__(self, name: object) -> bool:
        return name in self.names


# --- discovery ---------------------------------------------------------------


def find_definition(workspace: Path, *, home: Optional[Path] = None) -> Optional[Path]:
    """The nearest ``indexed.toml`` at or above ``workspace``, or ``None``.

    The walk stops before ``home`` so a definition dropped in the user's home
    directory cannot silently scope every project beneath it.
    """
    current = Path(workspace).expanduser()
    if current.is_file():
        current = current.parent
    current = current.resolve()
    boundary = (Path.home() if home is None else Path(home)).expanduser().resolve()
    while True:
        if current == boundary:
            return None
        candidate = current / SELECTION_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def find_git_root(workspace: Path) -> Optional[Path]:
    """The enclosing Git worktree root, or ``None``.

    ``.git`` is a directory in a normal checkout and a *file* inside a linked
    worktree; both count. This answers where a definition belongs to be written,
    not how one is resolved.
    """
    current = Path(workspace).expanduser()
    if current.is_file():
        current = current.parent
    current = current.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


# --- parsing -----------------------------------------------------------------


def read_definition(path: Path) -> tuple[str, ...]:
    """The raw ``[collections].use`` entries of a definition, in order.

    Raises :class:`WorkspaceSelectionError` naming the file and, where it
    applies, the offending key — a definition that cannot be read must never
    degrade into a wider or narrower scope.
    """
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkspaceSelectionError(
            f"Cannot read workspace definition '{path}': {exc}"
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise WorkspaceSelectionError(
            f"Workspace definition '{path}' is not valid TOML: {exc}"
        ) from exc

    version = raw.get("version")
    if version is None:
        raise WorkspaceSelectionError(
            f"Workspace definition '{path}' is missing the required 'version' key "
            f"(this indexed understands version {SELECTION_VERSION})."
        )
    if version != SELECTION_VERSION:
        raise WorkspaceSelectionError(
            f"Workspace definition '{path}' declares unsupported version {version} "
            f"(this indexed understands version {SELECTION_VERSION})."
        )

    collections = raw.get("collections")
    use = collections.get("use") if isinstance(collections, dict) else None
    if not isinstance(use, list) or not use:
        raise WorkspaceSelectionError(
            f"Workspace definition '{path}' needs a non-empty "
            "'[collections].use' array of collection names or ids."
        )

    entries: list[str] = []
    for entry in use:
        if not isinstance(entry, str) or not entry.strip():
            raise WorkspaceSelectionError(
                f"Workspace definition '{path}' has an invalid '[collections].use' "
                f"entry {entry!r}: expected a collection name or a stable id."
            )
        entries.append(entry.strip())
    return tuple(entries)


# --- resolution --------------------------------------------------------------


def _available_names(collections_path: Path) -> set[str]:
    """The collection names a store can actually serve (a dir with a manifest)."""
    root = Path(collections_path)
    if not root.is_dir():
        return set()
    return {child.name for child in root.iterdir() if (child / _MANIFEST).is_file()}


def resolve_entries(
    entries: Sequence[str],
    *,
    path: Path,
    registry: CollectionRegistry,
    collections_path: Path,
    strict: bool = True,
) -> tuple[tuple[SelectedCollection, ...], tuple[UnresolvedEntry, ...]]:
    """Turn raw entries into collections, or raise naming the offending entry.

    Broken *files* always raise: an unknown id form, a duplicate entry. A broken
    *store* — the collection or its data directory is gone — raises only when
    ``strict`` is on (every command but a search); with ``strict=False`` it is
    returned as an :class:`UnresolvedEntry` so a search can name it per source
    and still answer from the others (#340 R4).
    """
    available = _available_names(collections_path)
    resolved: list[SelectedCollection] = []
    unresolved: list[UnresolvedEntry] = []
    seen: set[str] = set()
    for position, entry in enumerate(entries):
        collection_id: Optional[str] = None
        if _STABLE_ID.match(entry):
            record = registry.by_id(entry)
            if record is None:
                reason = (
                    f"Workspace definition '{path}' selects collection id '{entry}', "
                    "which the shared registry does not know. Run `indexed collection "
                    "list` in this project for the ids it can select."
                )
                if strict:
                    raise WorkspaceSelectionError(reason)
                unresolved.append(
                    UnresolvedEntry(
                        entry=entry, name=entry, reason=reason, position=position
                    )
                )
                continue
            name = record.name
            collection_id = record.id
        else:
            name = entry
            record = registry.find(name)
            collection_id = record.id if record is not None else None

        if name in seen:
            raise WorkspaceSelectionError(
                f"Workspace definition '{path}' selects collection '{name}' twice; a "
                "selection is a set, so remove the repeated entry."
            )
        seen.add(name)

        if name not in available:
            reason = (
                f"Workspace definition '{path}' selects collection '{name}', which is "
                f"not in the store at '{collections_path}'. Run `indexed collection "
                "list` to see what this project can select."
            )
            if strict:
                raise WorkspaceSelectionError(reason)
            unresolved.append(
                UnresolvedEntry(
                    entry=entry, name=name, reason=reason, position=position
                )
            )
            continue

        resolved.append(
            SelectedCollection(name=name, id=collection_id, position=position)
        )
    return tuple(resolved), tuple(unresolved)


def load_selection(
    workspace: Path,
    *,
    registry: CollectionRegistry,
    collections_path: Path,
    home: Optional[Path] = None,
    strict: bool = True,
) -> Optional[WorkspaceSelection]:
    """Resolve the workspace's definition, or ``None`` when it has none."""
    path = find_definition(workspace, home=home)
    if path is None:
        return None
    collections, unresolved = resolve_entries(
        read_definition(path),
        path=path,
        registry=registry,
        collections_path=collections_path,
        strict=strict,
    )
    return WorkspaceSelection(
        path=path,
        root=path.parent,
        collections=collections,
        unresolved=unresolved,
    )


# --- writing (migration and rollback) ----------------------------------------


def render_definition(collection_ids: Sequence[str]) -> str:
    """Render a definition that selects ``collection_ids``.

    Written by ``indexed storage migrate``; ids are the canonical entry form
    because they survive a rename. Re-serialising drops hand-written comments —
    the generated header says so implicitly by replacing the whole file.
    """
    entries = "\n".join(f'  "{collection_id}",' for collection_id in collection_ids)
    return f"{_HEADER}\nversion = {SELECTION_VERSION}\n\n[collections]\nuse = [\n{entries}\n]\n"


def add_collection(root: Path, collection_id: str) -> Path:
    """Add ``collection_id`` to the definition at ``root``, creating it if needed."""
    path = Path(root) / SELECTION_FILENAME
    existing = read_definition(path) if path.is_file() else ()
    if collection_id in existing:
        return path
    path.write_text(render_definition((*existing, collection_id)), encoding="utf-8")
    return path


def remove_collection(root: Path, collection_id: str) -> bool:
    """Remove ``collection_id``; delete the definition when it was the last one."""
    path = Path(root) / SELECTION_FILENAME
    if not path.is_file():
        return False
    existing = read_definition(path)
    if collection_id not in existing:
        return False
    remaining = tuple(entry for entry in existing if entry != collection_id)
    if not remaining:
        path.unlink()
        return True
    path.write_text(render_definition(remaining), encoding="utf-8")
    return True
