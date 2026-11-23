"""System tests: the shared collection registry + local->global migration (#346).

Three acceptance properties, each able to go red:

1. ``test_two_workspaces_reuse_one_collection`` — a second project adopts the
   already-migrated collection instead of keeping its own copy: exactly one
   collection on disk, both workspaces search it.
2. ``test_dry_run_is_idempotent_and_resumable`` — a dry run twice reports the
   same plan and writes nothing; a migration interrupted after the data move
   resumes and finishes without duplicating anything.
3. ``test_rollback_restores_local_collection_and_engine_reads_correct_engine``
   — rollback puts the collection back, and the restored v2 store is queried
   through the engine (correct engine version, known hit) rather than checked
   for a file.

Real collections, real embeddings, CLI-driven — the same path a user takes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from indexed.cli.storage.commands import _migration
from indexed.config.collections_registry import CollectionRegistry
from indexed.config.storage import (
    get_collections_path,
    get_global_root,
    get_local_root,
    ensure_storage_dirs,
)
from indexed.config.workspace_selection import read_definition
from tests.conftest import model_available

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "shared-docs"
NEEDLE_QUERY = "penguin migration antarctic coastline"


@pytest.fixture(autouse=True)
def _clean_global_store():
    """Keep this module's registry + shared collections out of the sandbox HOME.

    The HOME sandbox is session-scoped, so without this the collection a first
    test migrated would look like a collision to the second one.
    """
    data = get_global_root() / "data"
    collections = data / "collections"
    pre_existing = (
        {child.name for child in collections.iterdir()}
        if collections.is_dir()
        else set()
    )

    def clean() -> None:
        (data / "registry.json").unlink(missing_ok=True)
        for journal in data.glob("registry-migration-*.json"):
            journal.unlink()
        if collections.is_dir():
            for child in collections.iterdir():
                if child.name not in pre_existing:
                    shutil.rmtree(child, ignore_errors=True)

    clean()
    yield
    clean()


def _workspace(path: Path) -> Path:
    """A project directory with its own ``./.indexed`` storage dirs.

    It is a Git worktree root because that is where the committed ``indexed.toml``
    belongs — ``storage migrate`` writes the definition there (#344).
    """
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    ensure_storage_dirs(get_local_root(path), is_local=True)
    return path


def _run(monkeypatch: pytest.MonkeyPatch, workspace: Path, args: list[str]):
    """Invoke the CLI from inside ``workspace`` and require success."""
    monkeypatch.chdir(workspace)
    result = runner.invoke(app, args)
    assert result.exit_code == 0, (
        f"`indexed {' '.join(args)}` failed in {workspace}:\n"
        f"{result.stdout}\n{result.stderr}"
    )
    return result


def _json_run(
    monkeypatch: pytest.MonkeyPatch, workspace: Path, args: list[str]
) -> dict:
    """Invoke the CLI with ``--simple-output`` and parse its JSON payload."""
    return json.loads(_run(monkeypatch, workspace, ["--simple-output", *args]).stdout)


def _create(
    monkeypatch, workspace: Path, corpus: Path, *, engine: str | None = None
) -> None:
    args = ["--log-level", "ERROR"]
    if engine is not None:
        args += ["--engine", engine]
    args += [
        "--local",
        "create",
        "files",
        "--collection",
        COLLECTION,
        "--path",
        str(corpus),
        "--local",
        "--no-cache",
    ]
    _run(monkeypatch, workspace, args)


def _search_ids(monkeypatch, workspace: Path) -> list[str]:
    payload = _json_run(
        monkeypatch,
        workspace,
        [
            "--local",
            "--log-level",
            "ERROR",
            "search",
            NEEDLE_QUERY,
            "--collection",
            COLLECTION,
            "--limit",
            "1",
        ],
    )
    return [doc["id"] for doc in payload["documents"]]


def _global_collection_dirs() -> list[Path]:
    root = get_collections_path(get_global_root())
    return sorted(
        child for child in root.glob("*") if (child / "manifest.json").is_file()
    )


def test_two_workspaces_reuse_one_collection(
    tmp_path: Path, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two projects point at ONE underlying collection — no second copy."""
    project_a = _workspace(tmp_path / "proj-a")
    project_b = _workspace(tmp_path / "proj-b")

    _create(monkeypatch, project_a, files_corpus)
    local_a = get_collections_path(get_local_root(project_a))
    local_b = get_collections_path(get_local_root(project_b))
    # Project B built its own copy before the registry existed.
    shutil.copytree(local_a / COLLECTION, local_b / COLLECTION)

    first = _json_run(
        monkeypatch, project_a, ["--log-level", "ERROR", "storage", "migrate"]
    )
    assert first["status"] == "migrate"

    # B's identical copy is reported as a collision and adopted on request.
    plan = _json_run(
        monkeypatch,
        project_b,
        ["--log-level", "ERROR", "storage", "migrate", "--dry-run"],
    )
    assert plan["collisions"] == 1

    adopted = _json_run(
        monkeypatch,
        project_b,
        ["--log-level", "ERROR", "storage", "migrate", "--on-collision", "adopt"],
    )
    assert [item["action"] for item in adopted["collections"]] == ["adopt"]

    # Exactly one copy exists, in the shared store; neither project keeps one.
    assert [path.name for path in _global_collection_dirs()] == [COLLECTION]
    assert not (local_a / COLLECTION).exists()
    assert not (local_b / COLLECTION).exists()

    registry = CollectionRegistry()
    records = [record for record in registry.records() if record.name == COLLECTION]
    assert len(records) == 1
    assert sorted(records[0].linked_workspaces) == sorted(
        [str(project_a.resolve()), str(project_b.resolve())]
    )
    definition_ids = {
        entry
        for project in (project_a, project_b)
        for entry in read_definition(project / "indexed.toml")
    }
    assert definition_ids == {records[0].id}

    # Both projects read the shared collection through the engine.
    assert _search_ids(monkeypatch, project_a) == ["needle.txt"]
    assert _search_ids(monkeypatch, project_b) == ["needle.txt"]


def test_dry_run_is_idempotent_and_resumable(
    tmp_path: Path, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dry run twice changes nothing; an interrupted run resumes cleanly."""
    project = _workspace(tmp_path / "proj")
    _create(monkeypatch, project, files_corpus)
    local = get_collections_path(get_local_root(project))
    registry = CollectionRegistry()
    journal = registry.journal_path_for(str(project.resolve()))

    first = _json_run(
        monkeypatch,
        project,
        ["--log-level", "ERROR", "storage", "migrate", "--dry-run"],
    )
    second = _json_run(
        monkeypatch,
        project,
        ["--log-level", "ERROR", "storage", "migrate", "--dry-run"],
    )
    assert first == second
    assert first["collections"][0]["action"] == "move"
    assert first["affected_bytes"] > 0
    # A dry run writes nothing at all.
    assert not registry.path.exists()
    assert not journal.exists()
    assert not _global_collection_dirs()
    assert (local / COLLECTION / "manifest.json").is_file()

    # Interrupt after the data move but before the step is recorded as done.
    real_move = shutil.move

    def crash_after_move(source: str, target: str) -> None:
        real_move(source, target)
        raise RuntimeError("simulated crash after the move")

    with pytest.MonkeyPatch.context() as fault:
        fault.setattr(_migration.shutil, "move", crash_after_move)
        with pytest.raises(RuntimeError):
            _migration.migrate(project)

    assert journal.is_file(), "the interrupted run must leave its journal behind"
    assert not (local / COLLECTION).exists()

    resumed = _json_run(
        monkeypatch, project, ["--log-level", "ERROR", "storage", "migrate"]
    )
    assert resumed["status"] == "migrate"
    assert resumed["resumed"] is True
    assert [path.name for path in _global_collection_dirs()] == [COLLECTION]
    record = registry.find(COLLECTION)
    assert record is not None
    assert read_definition(project / "indexed.toml") == (record.id,)

    # A second completed run is a no-op: no duplicate, no second id.
    again = _json_run(
        monkeypatch, project, ["--log-level", "ERROR", "storage", "migrate"]
    )
    assert again["status"] == "migrate"
    assert [path.name for path in _global_collection_dirs()] == [COLLECTION]
    assert [item.name for item in registry.records()] == [COLLECTION]

    assert _search_ids(monkeypatch, project) == ["needle.txt"]


def test_rollback_restores_local_collection_and_engine_reads_correct_engine(
    tmp_path: Path, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback restores the local v2 collection and it still answers queries."""
    from indexed.core.engine import engine_descriptors, search

    project = _workspace(tmp_path / "proj")
    _create(monkeypatch, project, files_corpus, engine="v2")
    local = get_collections_path(get_local_root(project))
    before = json.loads((local / COLLECTION / "manifest.json").read_text())
    assert before["version"] == "2"

    _json_run(monkeypatch, project, ["--log-level", "ERROR", "storage", "migrate"])
    assert not (local / COLLECTION).exists()
    assert [path.name for path in _global_collection_dirs()] == [COLLECTION]

    rolled_back = _json_run(
        monkeypatch,
        project,
        ["--log-level", "ERROR", "storage", "migrate", "--rollback"],
    )
    assert rolled_back["status"] == "rollback"

    # Restored in place, and the shared store no longer claims it.
    assert (
        json.loads((local / COLLECTION / "manifest.json").read_text())["version"] == "2"
    )
    assert [
        item for item in CollectionRegistry().records() if item.name == COLLECTION
    ] == []
    assert not (project / "indexed.toml").exists()
    assert _global_collection_dirs() == []

    # Through the engine: the right engine version, and a known hit.
    descriptors = engine_descriptors([COLLECTION], collections_path=str(local))
    assert [(item.name, item.engine_version) for item in descriptors] == [
        (COLLECTION, "2")
    ]
    results = search(NEEDLE_QUERY, collections_path=str(local), max_docs=1)
    assert results[COLLECTION]["results"][0]["id"] == "needle.txt"
