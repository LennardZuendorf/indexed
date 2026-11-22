"""Move a workspace's local collections into the shared global store (#346).

The contract, in one place:

* **Plan.** Enumerate the workspace's local collections (through the facade, so
  engine detection and the reserved-directory exclusions are the production
  ones), fingerprint each, and decide what would happen to it.
* **Migrate.** Journal every step to ``<global>/data/registry-migration-<ws>.json``
  BEFORE touching data, then move -> register -> select. Every step is
  idempotent and every step is reconcilable from the filesystem, so a run
  killed mid-way resumes instead of duplicating or losing a collection. The
  "select" step adds the collection's stable id to the committed
  ``indexed.toml`` at the Git worktree root (#344) — the repository's own
  artifact, not a workspace pointer.
* **Roll back.** Reverse the journal: put the data back where it was, drop the
  definition entry and the registry record. A collection that was *adopted* (the
  workspace held a byte-identical copy of one already in the store) is restored
  from the shared copy, because its local copy was removed on adoption — the
  shared collection itself is left alone for the workspaces still using it.

Fingerprints are structural (manifest bytes + the sorted file list with sizes),
not a byte hash of the whole tree: a dry run must stay cheap on a multi-GB FAISS
index, and the fingerprint only has to answer "is this the same collection?".
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from indexed.config.collections_registry import (
    REGISTRY_VERSION,
    CollectionRegistry,
    WorkspacePointers,
    utc_now,
    write_json_atomic,
)
from indexed.config.errors import StorageError
from indexed.config.storage import get_collections_path, get_local_root
from indexed.config.workspace_selection import (
    add_collection,
    find_git_root,
    remove_collection,
)

COLLISION_POLICIES = ("abort", "adopt", "rename")


class MigrationError(StorageError):
    """A migration step cannot proceed; the journal explains where it stopped."""


@dataclass(frozen=True)
class CollectionPlan:
    """What would happen to one local collection."""

    name: str
    engine: str
    source: str
    target: str
    size_bytes: int
    fingerprint: str
    action: str  # "move" | "adopt" | "conflict"
    collision: Optional[str] = None

    def to_dict(self) -> dict:
        """Plain dict for ``--simple-output`` and the journal."""
        return {
            "name": self.name,
            "engine": self.engine,
            "source": self.source,
            "target": self.target,
            "size_bytes": self.size_bytes,
            "action": self.action,
            "collision": self.collision,
        }


@dataclass(frozen=True)
class MigrationReport:
    """Outcome of a plan/migrate/rollback run (the CLI renders it)."""

    action: str  # "plan" | "migrate" | "rollback" | "noop"
    dry_run: bool
    workspace: str
    local_collections: str
    global_collections: str
    collections: tuple[CollectionPlan, ...] = field(default_factory=tuple)
    resumed: bool = False
    collisions: int = 0
    affected_bytes: int = 0
    messages: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        """JSON-ready payload shared by the JSON renderer and the tests."""
        return {
            "status": self.action,
            "dry_run": self.dry_run,
            "workspace": self.workspace,
            "local_collections": self.local_collections,
            "global_collections": self.global_collections,
            "resumed": self.resumed,
            "collisions": self.collisions,
            "affected_bytes": self.affected_bytes,
            "collections": [plan.to_dict() for plan in self.collections],
            "messages": list(self.messages),
        }


# --- discovery / fingerprints ------------------------------------------------


def fingerprint_collection(path: Path) -> str:
    """Structural fingerprint: manifest bytes plus every file's size."""
    digest = hashlib.sha256()
    manifest = path / "manifest.json"
    digest.update(manifest.read_bytes() if manifest.is_file() else b"")
    for entry in sorted(p for p in path.rglob("*") if p.is_file()):
        relative = entry.relative_to(path).as_posix()
        digest.update(f"{relative}\0{entry.stat().st_size}\n".encode())
    return digest.hexdigest()


def _tree_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())


def _describe_local(collections_path: Path) -> dict[str, str]:
    """``name -> engine`` for the workspace's local collections, via the facade.

    The facade owns engine detection and the reserved-sibling exclusions, so a
    migration can never see a collection the CLI cannot see. A directory the
    facade refuses to classify is a hard error here: silently skipping it would
    leave data behind while the workspace is repointed at the shared store.
    """
    from indexed.core.engine import engine_descriptors

    if not collections_path.is_dir():
        return {}
    descriptors = engine_descriptors(None, collections_path=str(collections_path))
    described = {
        descriptor.name: descriptor.engine_version for descriptor in descriptors
    }
    unreadable = sorted(
        child.name
        for child in collections_path.iterdir()
        if child.is_dir()
        and (child / "manifest.json").is_file()
        and child.name not in described
    )
    if unreadable:
        raise MigrationError(
            "Cannot classify collection(s) "
            + ", ".join(f"'{name}'" for name in unreadable)
            + " — their manifests are unreadable or carry an unknown version. "
            "Fix or remove them before migrating."
        )
    return described


def _relative_collection_path(global_collections: Path, target: Path) -> str:
    """The ``collections/<name>`` path recorded in the registry."""
    return target.relative_to(global_collections.parent).as_posix()


# --- planning ----------------------------------------------------------------


def plan(
    workspace: Path,
    *,
    on_collision: str = "abort",
    registry: Optional[CollectionRegistry] = None,
) -> MigrationReport:
    """Describe what ``migrate`` would do. Reads only — never writes."""
    if on_collision not in COLLISION_POLICIES:
        raise MigrationError(
            f"Unknown collision policy {on_collision!r}; "
            f"choose one of {', '.join(COLLISION_POLICIES)}."
        )
    workspace = Path(workspace)
    local_collections = get_collections_path(get_local_root(workspace))
    global_root = (registry or CollectionRegistry()).global_root
    global_collections = get_collections_path(global_root)
    described = _describe_local(local_collections)

    plans: list[CollectionPlan] = []
    for name in sorted(described):
        source = local_collections / name
        fingerprint = fingerprint_collection(source)
        target = global_collections / name
        action = "move"
        collision = None
        if target.exists():
            existing = fingerprint_collection(target)
            if existing == fingerprint:
                action = "conflict"
                collision = (
                    f"an identical copy is already in the shared store at '{target}'"
                )
                if on_collision == "adopt":
                    action = "adopt"
            else:
                action = "conflict"
                collision = (
                    f"a DIFFERENT collection named '{name}' is already in the "
                    f"shared store at '{target}'"
                )
                if on_collision == "rename":
                    suffix = fingerprint[:8]
                    renamed = global_collections / f"{name}-{suffix}"
                    if renamed.exists():
                        action = "conflict"
                        collision = (
                            f"{collision}; the fallback name '{renamed.name}' is "
                            f"taken too"
                        )
                    else:
                        target = renamed
                        action = "move"
                        collision = f"renamed to '{target.name}' ({collision})"
        plans.append(
            CollectionPlan(
                name=name,
                engine=described[name],
                source=str(source),
                target=str(target),
                size_bytes=_tree_size(source),
                fingerprint=fingerprint,
                action=action,
                collision=collision,
            )
        )

    return MigrationReport(
        action="plan",
        dry_run=True,
        workspace=str(workspace.resolve()),
        local_collections=str(local_collections),
        global_collections=str(global_collections),
        collections=tuple(plans),
        collisions=sum(1 for item in plans if item.action == "conflict"),
        affected_bytes=sum(item.size_bytes for item in plans),
    )


# --- journal -----------------------------------------------------------------


def _load_journal(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MigrationError(
            f"Cannot read the migration journal at '{path}': {exc}"
        ) from exc
    if str(raw.get("version")) != REGISTRY_VERSION:
        raise MigrationError(
            f"Unsupported migration journal version {raw.get('version')!r} at '{path}'."
        )
    return raw


def _save_journal(path: Path, journal: dict) -> None:
    write_json_atomic(path, journal)


def _step_by_name(journal: dict) -> list[dict]:
    steps = journal.get("steps")
    if not isinstance(steps, list):
        raise MigrationError("Malformed migration journal: 'steps' must be a list.")
    return steps


# --- moving ------------------------------------------------------------------


def _move_dir(source: Path, target: Path) -> None:
    """Move a collection directory, creating the target's parent first."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


def _reconcile(step: dict, *, action: str, fingerprint: str) -> None:
    """Bring a step's recorded state in line with what is actually on disk."""
    state = step["state"]
    if state in ("linked", "rolled_back"):
        return
    source = Path(step["source"])
    target = Path(step["target"])
    source_exists = source.is_dir()
    target_exists = target.is_dir()

    if target_exists and not source_exists:
        step["state"] = "moved"
        return
    if source_exists and not target_exists:
        step["state"] = "planned"
        return
    if source_exists and target_exists:
        source_print = fingerprint_collection(source)
        target_print = fingerprint_collection(target)
        if target_print == fingerprint and source_print == fingerprint:
            # An interrupted copy left two identical trees; the target wins.
            shutil.rmtree(source)
            step["state"] = "moved"
            return
        if action == "adopt" and target_print == fingerprint:
            shutil.rmtree(source)
            step["state"] = "moved"
            return
        if not (target / "manifest.json").is_file():
            # Partial copy from a cross-device move; the source is intact.
            shutil.rmtree(target)
            step["state"] = "planned"
            return
        raise MigrationError(
            f"Both '{source}' and '{target}' hold a collection named "
            f"'{step['name']}' and they differ. Resolve this by hand — the "
            f"migration will not choose one."
        )
    raise MigrationError(
        f"Collection '{step['name']}' is nowhere to be found: neither "
        f"'{step['source']}' nor '{step['target']}' exists."
    )


def _definition_root(workspace: Path) -> Path:
    """The Git worktree root the committed ``indexed.toml`` belongs to.

    A definition must belong to a repository: it is the portable artifact two
    clones share, so writing it into a bare directory would make it invisible
    to the next clone. Fail with the remedy instead of guessing a location.
    """
    root = find_git_root(workspace)
    if root is None:
        raise MigrationError(
            f"'{workspace}' is not inside a Git worktree. `indexed storage migrate` "
            "records the shared collections in a committed 'indexed.toml' at the "
            "repository root, so run it from the repository whose definition should "
            "list them."
        )
    return root


def migrate(
    workspace: Path,
    *,
    dry_run: bool = False,
    on_collision: str = "abort",
    registry: Optional[CollectionRegistry] = None,
) -> MigrationReport:
    """Move this workspace's local collections into the shared global store.

    A dry run performs zero writes and reports collisions. A real run journals
    every step first, so interrupting it and re-running resumes; running it
    again after it completed is a no-op. Each migrated collection is added to
    the committed ``indexed.toml`` at the Git worktree root — that definition,
    not a workspace pointer, is what tells this repository what it selects.
    """
    workspace = Path(workspace)
    registry = registry or CollectionRegistry()
    definition_root = _definition_root(workspace)
    pointers = WorkspacePointers(workspace)
    workspace_key = pointers.workspace_key()

    report = plan(workspace, on_collision=on_collision, registry=registry)
    journal_path = registry.journal_path_for(workspace_key)
    existing = _load_journal(journal_path)

    if dry_run:
        if existing is not None:
            # A dry run during an unfinished migration reports the journal's
            # steps (the disk no longer describes them) but still writes nothing.
            report = _journal_report(report, existing, action="plan")
        return replace(report, action="plan", dry_run=True)

    if existing is not None:
        return _resume(
            report,
            existing,
            journal_path=journal_path,
            registry=registry,
            workspace_key=workspace_key,
            global_collections=Path(report.global_collections),
            definition_root=definition_root,
        )

    if not report.collections:
        return replace(report, action="noop", dry_run=False)

    if report.collisions:
        raise MigrationError(
            "; ".join(
                f"'{item.name}': {item.collision}"
                for item in report.collections
                if item.action == "conflict"
            )
            + ". Re-run with --on-collision adopt (identical copy) or rename."
        )

    journal = {
        "version": REGISTRY_VERSION,
        "workspace": workspace_key,
        "definition": str(definition_root),
        "started_at": utc_now(),
        "completed_at": None,
        "steps": [
            {
                "name": item.name,
                "engine": item.engine,
                "source": item.source,
                "target": item.target,
                "action": item.action,
                "fingerprint": item.fingerprint,
                "id": None,
                "state": "planned",
            }
            for item in report.collections
        ],
    }
    _save_journal(journal_path, journal)
    return _run_steps(
        journal,
        journal_path=journal_path,
        registry=registry,
        workspace_key=workspace_key,
        global_collections=Path(report.global_collections),
        report=report,
        definition_root=definition_root,
    )


def _journal_report(
    report: MigrationReport,
    journal: dict,
    *,
    action: str,
    resumed: bool = False,
) -> MigrationReport:
    """Report the journal's steps — the only truth once a run has started.

    A resumed run cannot re-derive the plan from disk (already-moved sources are
    gone), so the journal is authoritative for name/target/action.
    """
    plans = tuple(
        CollectionPlan(
            name=step["name"],
            engine=step["engine"],
            source=step["source"],
            target=step["target"],
            size_bytes=_tree_size(Path(step["source"])),
            fingerprint=step["fingerprint"],
            action=step["action"],
        )
        for step in _step_by_name(journal)
    )
    return replace(
        report,
        collections=plans,
        action=action,
        resumed=resumed,
        affected_bytes=sum(item.size_bytes for item in plans),
    )


def _resume(
    report: MigrationReport,
    journal: dict,
    *,
    journal_path: Path,
    registry: CollectionRegistry,
    workspace_key: str,
    global_collections: Path,
    definition_root: Path,
) -> MigrationReport:
    """Continue an interrupted run from its journal (no re-planning)."""
    report = _journal_report(report, journal, action="migrate", resumed=True)
    return _run_steps(
        journal,
        journal_path=journal_path,
        registry=registry,
        workspace_key=workspace_key,
        global_collections=global_collections,
        report=report,
        definition_root=definition_root,
        resumed=True,
    )


def _run_steps(
    journal: dict,
    *,
    journal_path: Path,
    registry: CollectionRegistry,
    workspace_key: str,
    global_collections: Path,
    report: MigrationReport,
    definition_root: Path,
    resumed: bool = False,
) -> MigrationReport:
    """Drive every journal step to ``linked``, reconciling from disk each time."""
    pending = [step for step in _step_by_name(journal) if step["state"] != "linked"]
    for step in pending:
        _reconcile(
            step,
            action=step["action"],
            fingerprint=step["fingerprint"],
        )
        _save_journal(journal_path, journal)

        if step["state"] == "planned":
            _move_dir(Path(step["source"]), Path(step["target"]))
            step["state"] = "moved"
            _save_journal(journal_path, journal)

        record = registry.add(
            name=step["name"],
            engine=step["engine"],
            path=_relative_collection_path(global_collections, Path(step["target"])),
            workspace=workspace_key,
            fingerprint=step["fingerprint"],
            record_id=step.get("id"),
        )
        step["id"] = record.id
        step["state"] = "registered"
        _save_journal(journal_path, journal)

        add_collection(definition_root, record.id)
        registry.link_workspace(record.id, workspace_key)
        step["state"] = "linked"
        _save_journal(journal_path, journal)

    journal["completed_at"] = utc_now()
    _save_journal(journal_path, journal)
    return replace(report, action="migrate", dry_run=False, resumed=resumed)


# --- rollback ----------------------------------------------------------------


def rollback(
    workspace: Path,
    *,
    registry: Optional[CollectionRegistry] = None,
) -> MigrationReport:
    """Undo this workspace's migration, restoring its local collections."""
    workspace = Path(workspace)
    registry = registry or CollectionRegistry()
    pointers = WorkspacePointers(workspace)
    workspace_key = pointers.workspace_key()
    journal_path = registry.journal_path_for(workspace_key)
    journal = _load_journal(journal_path)
    if journal is None or journal.get("workspace") != workspace_key:
        raise MigrationError(
            "No migration to roll back for this workspace "
            f"(looked for a journal at '{journal_path}')."
        )

    local_collections = get_collections_path(get_local_root(workspace))
    global_collections = get_collections_path(registry.global_root)
    definition_root = find_git_root(workspace)
    messages: list[str] = []
    plans: list[CollectionPlan] = []

    for step in reversed(_step_by_name(journal)):
        if step["state"] == "rolled_back":
            continue
        source = Path(step["source"])
        target = Path(step["target"])
        collection_id = step.get("id")

        # Both artifacts are undone: the definition entry this migration added
        # (deleting the file when it was the only one) and, for workspaces
        # migrated under #346, the legacy pointer — left behind it would keep
        # routing at a store that no longer holds the collection.
        pointers.unlink(step["name"])
        if collection_id and definition_root is not None:
            remove_collection(definition_root, collection_id)
        if collection_id:
            registry.unlink_workspace(collection_id, workspace_key)
            if step["action"] != "adopt":
                registry.remove(collection_id)

        if step["action"] == "adopt":
            if not source.exists() and target.is_dir():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(target, source)
                messages.append(
                    f"{step['name']}: restored from the shared copy "
                    "(the local copy was removed on adoption)."
                )
            elif not source.exists():
                raise MigrationError(
                    f"Rollback cannot restore '{step['name']}': its local copy is "
                    f"gone and the shared copy at '{target}' is no longer there "
                    "(another workspace rolled its migration back first)."
                )
        elif target.is_dir() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            _move_dir(target, source)
        elif target.is_dir() and source.is_dir():
            if fingerprint_collection(target) == fingerprint_collection(source):
                shutil.rmtree(target)
            else:
                raise MigrationError(
                    f"Rollback cannot restore '{step['name']}': both '{source}' "
                    f"and '{target}' exist and they differ."
                )

        step["state"] = "rolled_back"
        _save_journal(journal_path, journal)
        plans.append(
            CollectionPlan(
                name=step["name"],
                engine=step["engine"],
                source=step["source"],
                target=step["target"],
                size_bytes=_tree_size(source),
                fingerprint=step["fingerprint"],
                action=step["action"],
            )
        )

    journal_path.unlink(missing_ok=True)
    return MigrationReport(
        action="rollback",
        dry_run=False,
        workspace=workspace_key,
        local_collections=str(local_collections),
        global_collections=str(global_collections),
        collections=tuple(plans),
        affected_bytes=sum(item.size_bytes for item in plans),
        messages=tuple(messages),
    )


def describe_journal(path: Path) -> Optional[dict]:
    """Expose the journal for diagnostics/tests without importing privates."""
    return _load_journal(path)
