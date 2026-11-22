"""Unit tests for the shared-store migration's planning and collision rules.

Fake collection directories + a stubbed descriptor lookup keep this about the
decision table (move / adopt / conflict / rename) without embedding a model.
The end-to-end behaviour lives in ``tests/system/test_collection_registry.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from indexed.cli.storage.commands import _migration
from indexed.config.collections_registry import CollectionRegistry


def _fake_collection(root: Path, name: str, *, body: str = "payload") -> Path:
    """A minimal collection the facade would classify as v1."""
    path = root / name
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(
        json.dumps({"collectionName": name, "indexers": [{"name": "faiss"}]})
    )
    (path / "documents.json").write_text(json.dumps({"body": body}))
    return path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace whose descriptors are stubbed to the fake manifests on disk."""
    project = tmp_path / "proj"
    (project / ".indexed" / "data" / "collections").mkdir(parents=True)
    # The definition migrate writes belongs at a Git worktree root (#344).
    (project / ".git").mkdir()
    monkeypatch.setattr(
        _migration,
        "_describe_local",
        lambda path: (
            {
                child.name: "1"
                for child in sorted(path.iterdir())
                if (child / "manifest.json").is_file()
            }
            if path.is_dir()
            else {}
        ),
    )
    return project


@pytest.fixture
def registry(tmp_path: Path) -> CollectionRegistry:
    return CollectionRegistry(tmp_path / "global")


def test_plan_reports_collision_kinds_without_writing(
    workspace: Path, registry: CollectionRegistry
) -> None:
    local = workspace / ".indexed" / "data" / "collections"
    _fake_collection(local, "same")
    _fake_collection(local, "different")
    shared = registry.global_root / "data" / "collections"
    _fake_collection(shared, "same")
    differing = _fake_collection(shared, "different")
    (differing / "documents.json").write_text(json.dumps({"body": "other"}))

    report = _migration.plan(workspace, registry=registry)

    by_name = {item.name: item for item in report.collections}
    assert by_name["same"].collision is not None
    assert "identical copy" in by_name["same"].collision
    assert by_name["different"].action == "conflict"
    assert "DIFFERENT collection" in by_name["different"].collision
    assert report.collisions == 2
    assert report.affected_bytes > 0
    assert not registry.path.exists()


def test_adopt_policy_marks_identical_copies(
    workspace: Path, registry: CollectionRegistry
) -> None:
    local = workspace / ".indexed" / "data" / "collections"
    _fake_collection(local, "docs")
    _fake_collection(registry.global_root / "data" / "collections", "docs")

    report = _migration.plan(workspace, on_collision="adopt", registry=registry)
    assert [item.action for item in report.collections] == ["adopt"]


def test_rename_policy_targets_a_distinct_name(
    workspace: Path, registry: CollectionRegistry
) -> None:
    local = workspace / ".indexed" / "data" / "collections"
    _fake_collection(local, "docs")
    shared = _fake_collection(registry.global_root / "data" / "collections", "docs")
    (shared / "documents.json").write_text(json.dumps({"body": "other"}))

    report = _migration.plan(workspace, on_collision="rename", registry=registry)
    target = report.collections[0].target
    assert report.collections[0].action == "move"
    assert Path(target).name.startswith("docs-")
    assert Path(target).name != "docs"


def test_unknown_collision_policy_is_refused(
    workspace: Path, registry: CollectionRegistry
) -> None:
    with pytest.raises(_migration.MigrationError, match="Unknown collision policy"):
        _migration.plan(workspace, on_collision="merge", registry=registry)


def test_real_migration_refuses_collisions_before_touching_data(
    workspace: Path, registry: CollectionRegistry
) -> None:
    local = workspace / ".indexed" / "data" / "collections"
    _fake_collection(local, "docs")
    shared = _fake_collection(registry.global_root / "data" / "collections", "docs")
    (shared / "documents.json").write_text(json.dumps({"body": "other"}))

    with pytest.raises(_migration.MigrationError, match="on-collision"):
        _migration.migrate(workspace, registry=registry)

    # Nothing moved, nothing was registered.
    assert (local / "docs" / "manifest.json").is_file()
    assert not registry.path.exists()


# --- the committed definition (#344) -----------------------------------------


def test_migrate_writes_the_definition_at_the_git_root(
    workspace: Path, registry: CollectionRegistry
) -> None:
    """The selection, not a pointer, is what the repository keeps."""
    _fake_collection(workspace / ".indexed" / "data" / "collections", "docs")

    report = _migration.migrate(workspace, registry=registry)

    assert report.action == "migrate"
    definition = workspace / "indexed.toml"
    assert definition.is_file()
    record = registry.find("docs")
    assert record is not None
    assert record.id in definition.read_text(encoding="utf-8")
    # The pointer is legacy: this run must not create one.
    assert not (workspace / ".indexed" / "collections.json").exists()


def test_migrate_writes_the_definition_above_a_nested_workspace(
    workspace: Path, registry: CollectionRegistry
) -> None:
    """Running from a subdirectory still defines the repository, not the subdir."""
    nested = workspace / "src" / "pkg"
    _fake_collection(nested / ".indexed" / "data" / "collections", "docs")

    _migration.migrate(nested, registry=registry)

    assert (workspace / "indexed.toml").is_file()
    assert not (nested / "indexed.toml").exists()


def test_migrate_refuses_a_directory_outside_git(
    tmp_path: Path, registry: CollectionRegistry
) -> None:
    """A definition must belong to a repository, so this fails with the remedy."""
    project = tmp_path / "plain"
    _fake_collection(project / ".indexed" / "data" / "collections", "docs")

    with pytest.raises(_migration.MigrationError, match="not inside a Git worktree"):
        _migration.migrate(project, registry=registry)


def test_rollback_removes_its_entry_then_deletes_the_definition(
    workspace: Path, registry: CollectionRegistry
) -> None:
    _fake_collection(workspace / ".indexed" / "data" / "collections", "docs")
    _migration.migrate(workspace, registry=registry)
    definition = workspace / "indexed.toml"
    assert definition.is_file()

    _migration.rollback(workspace, registry=registry)

    # The entry was the only one, so the file goes with it.
    assert not definition.exists()
