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

    assert (local / "docs" / "manifest.json").is_file()
    assert not registry.path.exists()
