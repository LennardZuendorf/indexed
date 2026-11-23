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


# --- --verify=structural|hash -------------------------------------------------


def _same_shape_pair(
    workspace: Path, registry: CollectionRegistry
) -> tuple[Path, Path]:
    """Local + shared 'docs': identical names and sizes, different bytes."""
    local = _fake_collection(
        workspace / ".indexed" / "data" / "collections", "docs", body="aaaa"
    )
    shared = _fake_collection(
        registry.global_root / "data" / "collections", "docs", body="bbbb"
    )
    for name in ("documents.json", "manifest.json"):
        assert (local / name).stat().st_size == (shared / name).stat().st_size
    assert (local / "documents.json").read_bytes() != (
        shared / "documents.json"
    ).read_bytes()
    return local, shared


def test_structural_verify_cannot_tell_same_size_collections_apart(
    workspace: Path, registry: CollectionRegistry
) -> None:
    """Documents the weakness: structural calls them identical and adopts."""
    _same_shape_pair(workspace, registry)

    report = _migration.plan(
        workspace, on_collision="adopt", registry=registry, verify="structural"
    )

    assert [item.action for item in report.collections] == ["adopt"]


def test_hash_verify_refuses_same_size_collections_and_names_the_file(
    workspace: Path, registry: CollectionRegistry
) -> None:
    local, shared = _same_shape_pair(workspace, registry)

    report = _migration.plan(workspace, registry=registry, verify="hash")
    assert [item.action for item in report.collections] == ["conflict"]
    assert "documents.json" in (report.collections[0].collision or "")

    with pytest.raises(_migration.MigrationError, match="documents.json"):
        _migration.migrate(workspace, registry=registry, verify="hash")
    assert (local / "documents.json").is_file()
    assert not registry.path.exists()


def test_adopt_with_hash_never_deletes_a_mismatching_local_copy(
    workspace: Path, registry: CollectionRegistry
) -> None:
    local, shared = _same_shape_pair(workspace, registry)

    with pytest.raises(_migration.MigrationError, match="documents.json"):
        _migration.migrate(
            workspace, on_collision="adopt", registry=registry, verify="hash"
        )

    assert (local / "documents.json").read_text() == '{"body": "aaaa"}'
    assert (shared / "documents.json").read_text() == '{"body": "bbbb"}'


def test_adopt_reconcile_with_hash_keeps_a_source_that_drifted(
    tmp_path: Path,
) -> None:
    """Resume path: the journaled print matches the target but not the source."""
    source = _fake_collection(tmp_path / "local", "docs", body="aaaa")
    target = _fake_collection(tmp_path / "shared", "docs", body="bbbb")
    step = {
        "name": "docs",
        "source": str(source),
        "target": str(target),
        "state": "planned",
    }
    journaled = _migration.fingerprint_collection(target, "hash")

    with pytest.raises(_migration.MigrationError, match="differ"):
        _migration._reconcile(
            step, action="adopt", fingerprint=journaled, verify="hash"
        )

    assert source.is_dir()


@pytest.mark.parametrize(
    ("verify", "justification"),
    [("structural", "structural"), ("hash", "content hash")],
)
def test_adopting_an_identical_copy_logs_which_check_justified_the_delete(
    workspace: Path,
    registry: CollectionRegistry,
    caplog: pytest.LogCaptureFixture,
    verify: str,
    justification: str,
) -> None:
    local = _fake_collection(workspace / ".indexed" / "data" / "collections", "docs")
    _fake_collection(registry.global_root / "data" / "collections", "docs")

    with caplog.at_level("INFO", logger=_migration.logger.name):
        _migration.migrate(
            workspace, on_collision="adopt", registry=registry, verify=verify
        )

    assert not local.exists()
    lines = [
        r.getMessage() for r in caplog.records if "Removed local" in r.getMessage()
    ]
    assert len(lines) == 1
    assert justification in lines[0]
    # Under workspace selection (#372) the migrated collection is selected by
    # the committed definition, not by the deprecated local pointer.
    definition = workspace / "indexed.toml"
    assert definition.is_file()
    record = registry.find("docs")
    assert record is not None
    assert record.id in definition.read_text(encoding="utf-8")


def test_hash_verify_checks_the_moved_bytes_against_the_planned_content(
    workspace: Path, registry: CollectionRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_collection(workspace / ".indexed" / "data" / "collections", "docs")
    real_move = _migration._move_dir

    def corrupting_move(source: Path, target: Path) -> None:
        real_move(source, target)
        (target / "documents.json").write_text(json.dumps({"body": "garbage"[:7]}))

    monkeypatch.setattr(_migration, "_move_dir", corrupting_move)
    # "payload" and "garbage" are both 7 bytes: only a content check sees it.
    with pytest.raises(_migration.MigrationError, match="documents.json|content"):
        _migration.migrate(workspace, registry=registry, verify="hash")
    assert not registry.path.exists()


def test_structural_verify_misses_the_same_corruption(
    workspace: Path, registry: CollectionRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_collection(workspace / ".indexed" / "data" / "collections", "docs")
    real_move = _migration._move_dir

    def corrupting_move(source: Path, target: Path) -> None:
        real_move(source, target)
        (target / "documents.json").write_text(json.dumps({"body": "garbage"[:7]}))

    monkeypatch.setattr(_migration, "_move_dir", corrupting_move)
    report = _migration.migrate(workspace, registry=registry)
    assert report.action == "migrate"


def test_unknown_verify_mode_is_refused(
    workspace: Path, registry: CollectionRegistry
) -> None:
    with pytest.raises(_migration.MigrationError, match="Unknown verify mode"):
        _migration.plan(workspace, registry=registry, verify="md5")


def test_resume_cannot_switch_verify_mode(
    workspace: Path, registry: CollectionRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_collection(workspace / ".indexed" / "data" / "collections", "docs")

    def boom(source: Path, target: Path) -> None:
        raise OSError("killed")

    monkeypatch.setattr(_migration, "_move_dir", boom)
    with pytest.raises(OSError):
        _migration.migrate(workspace, registry=registry, verify="hash")
    monkeypatch.undo()

    with pytest.raises(_migration.MigrationError, match="--verify=hash"):
        _migration.migrate(workspace, registry=registry, verify="structural")
    # no flag -> the journal's mode is used, and the run completes
    assert _migration.migrate(workspace, registry=registry).resumed


def test_hashing_reads_in_bounded_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"x" * 10_000)
    monkeypatch.setattr(_migration, "HASH_CHUNK_BYTES", 1024)
    reads: list[int] = []
    real_open = Path.open

    def spying_open(self: Path, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        if self != path:
            return handle

        class Spy:
            def __enter__(self_inner):
                handle.__enter__()
                return self_inner

            def __exit__(self_inner, *exc):
                return handle.__exit__(*exc)

            def read(self_inner, size: int = -1):
                reads.append(size)
                return handle.read(size)

        return Spy()

    monkeypatch.setattr(Path, "open", spying_open)
    _migration._hash_file(path)
    assert reads and all(0 < size <= 1024 for size in reads)


def test_hash_verify_peak_memory_stays_bounded_on_a_large_file(
    tmp_path: Path,
) -> None:
    """A whole-file read of 512 MiB would add >=512 MiB of peak RSS."""
    import subprocess
    import sys
    import textwrap

    collection = _fake_collection(tmp_path, "big")
    with (collection / "index.faiss").open("wb") as handle:
        handle.truncate(512 * 1024 * 1024)  # sparse; reads back as zeros
    script = textwrap.dedent(
        f"""
        import resource, sys
        from pathlib import Path
        from indexed.cli.storage.commands import _migration
        before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        _migration.fingerprint_collection(Path({str(collection)!r}), "hash")
        after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        scale = 1 if sys.platform == "darwin" else 1024
        print((after - before) * scale)
        """
    )
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert int(done.stdout.strip()) < 64 * 1024 * 1024


def test_cli_help_and_validation_state_the_verify_default() -> None:
    import re

    from typer.testing import CliRunner

    from indexed.cli.app import app

    runner = CliRunner()
    helped = runner.invoke(app, ["storage", "migrate", "--help"])
    # Rich wraps every flag in ANSI colour codes when the environment asks for colour
    # (CI does), so the literal "--verify" is not contiguous in the raw output. Strip the
    # escape sequences: the assertion is about the help text, not the renderer.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", helped.output)
    flat = " ".join(plain.split())
    assert "--verify" in flat
    assert "structural (default" in flat
    assert "does NOT compare content" in flat

    refused = runner.invoke(app, ["storage", "migrate", "--verify", "md5"])
    assert refused.exit_code == 1
    assert "Unknown verify mode" in " ".join(refused.output.split())


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
