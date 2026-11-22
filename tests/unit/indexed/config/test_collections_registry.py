"""Unit tests for the global collection registry and workspace pointers (#346).

No collections are involved: these pin the bookkeeping contract — stable ids,
one record per name, loud failures on an unreadable or future-versioned file,
and pointer behaviour when the shared root has disappeared.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from indexed.config.collections_registry import (
    CollectionRegistry,
    CollectionRegistryError,
    CollectionRecord,
    WorkspacePointers,
    write_json_atomic,
)


@pytest.fixture
def global_root(tmp_path: Path) -> Path:
    return tmp_path / "global"


def test_id_is_stable_across_reloads_and_repeated_registration(
    global_root: Path,
) -> None:
    """One collection keeps its id: re-register, reload, rename nothing."""
    registry = CollectionRegistry(global_root)
    record = registry.add(
        name="docs", engine="2", path="collections/docs", workspace="/proj/a"
    )
    assert len(record.id) == 32

    again = registry.add(
        name="docs", engine="2", path="collections/docs", workspace="/proj/a"
    )
    assert again.id == record.id
    assert [item.id for item in CollectionRegistry(global_root).records()] == [
        record.id
    ]


def test_same_name_at_a_different_path_is_refused(global_root: Path) -> None:
    """A name is the identity callers resolve; never retarget it silently."""
    registry = CollectionRegistry(global_root)
    registry.add(name="docs", engine="1", path="collections/docs", workspace="/a")
    with pytest.raises(CollectionRegistryError, match="already registered"):
        registry.add(
            name="docs", engine="1", path="collections/docs-renamed", workspace="/b"
        )


def test_unknown_registry_version_fails_loud(global_root: Path) -> None:
    """A future registry is an error, not an empty registry (that would copy)."""
    registry = CollectionRegistry(global_root)
    registry.path.parent.mkdir(parents=True)
    registry.path.write_text(json.dumps({"version": "9", "collections": []}))
    with pytest.raises(CollectionRegistryError, match="version"):
        registry.records()


def test_unreadable_registry_fails_loud(global_root: Path) -> None:
    registry = CollectionRegistry(global_root)
    registry.path.parent.mkdir(parents=True)
    registry.path.write_text("{not json")
    with pytest.raises(CollectionRegistryError, match="Cannot read"):
        registry.records()


def test_duplicate_ids_are_rejected(global_root: Path) -> None:
    registry = CollectionRegistry(global_root)
    entry = CollectionRecord(
        id="deadbeef",
        name="a",
        engine="1",
        path="collections/a",
        workspace="/a",
        registered_at="2026-01-01T00:00:00+00:00",
    )
    write_json_atomic(
        registry.path,
        {
            "version": "1",
            "collections": [
                entry.to_disk(),
                {**entry.to_disk(), "name": "b", "path": "collections/b"},
            ],
        },
    )
    with pytest.raises(CollectionRegistryError, match="duplicate"):
        registry.records()


def test_link_and_unlink_workspace_are_idempotent(global_root: Path) -> None:
    registry = CollectionRegistry(global_root)
    record = registry.add(
        name="docs", engine="1", path="collections/docs", workspace="/a"
    )
    registry.link_workspace(record.id, "/b")
    registry.link_workspace(record.id, "/b")
    assert registry.by_id(record.id).linked_workspaces == ("/b",)
    registry.unlink_workspace(record.id, "/b")
    registry.unlink_workspace(record.id, "/b")
    assert registry.by_id(record.id).linked_workspaces == ()


def test_remove_deletes_the_file_once_empty(global_root: Path) -> None:
    registry = CollectionRegistry(global_root)
    record = registry.add(
        name="docs", engine="1", path="collections/docs", workspace="/a"
    )
    assert registry.remove(record.id) is True
    assert registry.remove(record.id) is False
    assert not registry.path.exists()


def test_pointer_round_trip_and_missing_root(tmp_path: Path) -> None:
    workspace = tmp_path / "proj"
    shared = tmp_path / "global" / "data" / "collections"
    shared.mkdir(parents=True)
    pointers = WorkspacePointers(workspace)

    assert pointers.shared_root() is None
    pointers.link("docs", "abc123", shared)
    assert pointers.shared_root() == shared
    assert pointers.resolve("docs") == "abc123"
    assert pointers.resolve("other") is None

    pointers.unlink("docs")
    assert pointers.resolve("docs") is None
    assert not pointers.path.exists()


def test_pointer_to_a_vanished_root_is_ignored(tmp_path: Path) -> None:
    """A stale pointer must not brick every command in the workspace."""
    workspace = tmp_path / "proj"
    gone = tmp_path / "gone" / "collections"
    pointers = WorkspacePointers(workspace)
    pointers.link("docs", "abc123", gone)
    assert pointers.shared_root() is None


def test_journal_path_is_per_workspace(global_root: Path) -> None:
    registry = CollectionRegistry(global_root)
    first = registry.journal_path_for("/proj/a")
    second = registry.journal_path_for("/proj/b")
    assert first != second
    assert first.parent == global_root / "data"
