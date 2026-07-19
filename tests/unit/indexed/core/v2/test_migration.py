"""v1 -> v2 migration service tests (core-v2/4, R7).

Model-FREE: ``mock_embedding`` patches ``build_embed_model`` (both the staging
build and the validation probe resolve it from ``embedding.local``), so no model
download/load is needed. A real v1 collection is written on disk in the exact v1
layout (``manifest.json`` without a ``version`` key + ``documents/<id>.json``),
so the offline path reads genuine stored content.

Covers the R7 scenarios at the service level: dry-run changes nothing; a failed
migration leaves v1 intact with no partial v2; offline migration needs no source
access; rollback restores the v1 dir byte-identical. Post-migration SEARCH parity
(needle top hit) needs real embeddings and lives in the system test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from indexed.core.errors import CoreV2Error
from indexed.core.v2 import migration

from tests.unit.indexed.core.v2._engine_helpers import make_doc, mock_embedding


# --- fixtures / helpers ------------------------------------------------------


def _write_v1_collection(
    base: Path, name: str, docs: list[dict], *, reader: dict | None = None
) -> Path:
    """Write a real v1-layout collection: manifest.json (no version) + documents/."""
    coll = base / name
    (coll / "documents").mkdir(parents=True, exist_ok=True)
    num_chunks = sum(len(d.get("chunks") or []) for d in docs)
    manifest = {
        "collectionName": name,
        "createdTime": "2026-01-01T00:00:00+00:00",
        "updatedTime": "2026-01-02T00:00:00+00:00",
        "lastModifiedDocumentTime": "2026-01-02T00:00:00+00:00",
        "numberOfDocuments": len(docs),
        "numberOfChunks": num_chunks,
        "reader": reader or {"type": "localFiles", "basePath": "/corpus"},
        "indexers": [
            {"name": "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"}
        ],
    }
    (coll / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    for doc in docs:
        (coll / "documents" / f"{doc['id']}.json").write_text(
            json.dumps(doc, indent=2), encoding="utf-8"
        )
    return coll


def _dir_fingerprint(root: Path) -> dict[str, str]:
    """Map each file's relative path -> sha256 of its bytes (for byte-identity)."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(root))
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _corpus() -> list[dict]:
    return [
        make_doc("alpha.txt", ["semantic search finds documents by meaning"]),
        make_doc(
            "needle.txt", ["penguin migration survey antarctic coastline", "more"]
        ),
    ]


# --- R7 scenario 1: dry-run changes nothing ----------------------------------


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    coll = _write_v1_collection(base, "c1", _corpus())
    before = _dir_fingerprint(coll)

    with mock_embedding(embed_dim=8):
        result = migration.migrate("c1", collections_path=str(base), dry_run=True)

    assert result.dry_run is True
    assert result.action == "dry-run"
    assert result.number_of_documents == 2
    assert result.number_of_chunks == 3
    assert "MiniLM" in result.embedding_model
    assert result.vector_store == "simple"
    # No file changed, no backup, no staging dir created.
    assert _dir_fingerprint(coll) == before
    assert not (base / "c1.v1-backup").exists()
    assert [p.name for p in base.iterdir()] == ["c1"]


# --- R7 scenario 3: offline migration without source access ------------------


def test_offline_migration_builds_v2_and_keeps_backup(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    _write_v1_collection(base, "c1", _corpus())
    v1_before = _dir_fingerprint(base / "c1")

    # No manifest_factory / connector_factory supplied — proves the default path
    # needs no source access (R7 offline scenario).
    with mock_embedding(embed_dim=8):
        result = migration.migrate("c1", collections_path=str(base))

    assert result.action == "migrate"
    assert result.validated is True
    assert result.number_of_documents == 2
    assert result.number_of_chunks == 3

    # <name> is now a v2 collection with the storage/ layout.
    manifest = json.loads((base / "c1" / "manifest.json").read_text())
    assert manifest["version"] == "2"
    assert manifest["engine"]["vectorStore"] == "simple"
    assert manifest["reader"]["type"] == "localFiles"  # reader block reused verbatim
    assert manifest["createdTime"] == "2026-01-01T00:00:00+00:00"  # preserved
    storage = {p.name for p in (base / "c1" / "storage").iterdir()}
    assert {
        "docstore.json",
        "index_store.json",
        "default__vector_store.json",
    } <= storage

    # The v1 collection is preserved byte-for-byte as the backup.
    backup = base / "c1.v1-backup"
    assert backup.is_dir()
    assert result.backup_path == str(backup)
    assert _dir_fingerprint(backup) == v1_before
    # No staging dir survives.
    assert not any(".tmp-" in p.name for p in base.iterdir())


# --- R7 scenario 2: failed migration leaves v1 intact, no partial v2 ---------


def test_failed_validation_leaves_v1_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "cols"
    coll = _write_v1_collection(base, "c1", _corpus())
    before = _dir_fingerprint(coll)

    def _boom(*args, **kwargs):
        raise CoreV2Error("validation boom")

    monkeypatch.setattr(migration, "_validate_migration", _boom)

    with mock_embedding(embed_dim=8):
        with pytest.raises(CoreV2Error, match="validation boom"):
            migration.migrate("c1", collections_path=str(base))

    # v1 fully intact; no backup, no partial v2, no staging left behind.
    assert _dir_fingerprint(coll) == before
    assert not (base / "c1.v1-backup").exists()
    assert [p.name for p in base.iterdir()] == ["c1"]


# --- R7 scenario 5: rollback restores byte-identical v1 ----------------------


def test_rollback_restores_byte_identical_v1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "cols"
    coll = _write_v1_collection(base, "c1", _corpus())
    before = _dir_fingerprint(coll)

    # Fail the final staging->dest swap AFTER the backup rename succeeded, so the
    # rollback (rename backup back) path runs.
    def _boom_swap(staging, dest):
        raise RuntimeError("swap boom")

    monkeypatch.setattr(migration, "_swap", _boom_swap)

    with mock_embedding(embed_dim=8):
        with pytest.raises(RuntimeError, match="swap boom"):
            migration.migrate("c1", collections_path=str(base))

    # The original v1 dir was renamed back into place, byte-identical.
    assert (base / "c1").is_dir()
    assert _dir_fingerprint(base / "c1") == before
    # Neither the backup nor the staging dir survive after rollback.
    assert not (base / "c1.v1-backup").exists()
    assert not any(".tmp-" in p.name for p in base.iterdir())


# --- edge cases --------------------------------------------------------------


def test_migrate_missing_collection_errors(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    base.mkdir()
    with pytest.raises(CoreV2Error, match="does not exist"):
        migration.migrate("ghost", collections_path=str(base))


def test_migrate_already_v2_errors(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    # Build a v2 collection first (via a real offline migration).
    _write_v1_collection(base, "c1", _corpus())
    with mock_embedding(embed_dim=8):
        migration.migrate("c1", collections_path=str(base), purge_backup=True)
    # Now it's v2 → migrating again is a clear error.
    with pytest.raises(CoreV2Error, match="already a v2 collection"):
        migration.migrate("c1", collections_path=str(base))


def test_backup_collision_errors(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    _write_v1_collection(base, "c1", _corpus())
    (base / "c1.v1-backup").mkdir()  # stale backup blocks the swap
    with mock_embedding(embed_dim=8):
        with pytest.raises(CoreV2Error, match="backup already exists"):
            migration.migrate("c1", collections_path=str(base))
    # v1 untouched, still v1.
    assert "version" not in json.loads((base / "c1" / "manifest.json").read_text())


def test_purge_backup_after_migration_removes_backup(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    _write_v1_collection(base, "c1", _corpus())
    with mock_embedding(embed_dim=8):
        result = migration.migrate("c1", collections_path=str(base), purge_backup=True)
    assert result.backup_purged is True
    assert result.backup_path is None
    assert not (base / "c1.v1-backup").exists()
    assert json.loads((base / "c1" / "manifest.json").read_text())["version"] == "2"


def test_purge_backup_standalone_on_migrated_collection(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    _write_v1_collection(base, "c1", _corpus())
    with mock_embedding(embed_dim=8):
        migration.migrate("c1", collections_path=str(base))  # keeps backup
    assert (base / "c1.v1-backup").is_dir()

    # A second call with --purge-backup on the now-v2 collection cleans it up.
    result = migration.migrate("c1", collections_path=str(base), purge_backup=True)
    assert result.action == "purge-backup"
    assert result.backup_purged is True
    assert not (base / "c1.v1-backup").exists()


def test_from_source_requires_manifest_factory(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    _write_v1_collection(base, "c1", _corpus())
    with pytest.raises(CoreV2Error, match="--from-source requires"):
        migration.migrate("c1", collections_path=str(base), from_source=True)


def test_from_source_rebuilds_from_live_source(tmp_path: Path) -> None:
    """--from-source re-reads via manifest_factory (full corpus), not stored docs."""
    from tests.unit.indexed.core.v2._engine_helpers import (
        make_update_manifest_factory,
    )

    base = tmp_path / "cols"
    # Stored (offline) content differs from what the "live source" returns, so we
    # can prove the source path was used.
    _write_v1_collection(base, "c1", [make_doc("stored.txt", ["old stored content"])])
    fresh = [
        make_doc("fresh_a.txt", ["fresh source alpha"]),
        make_doc("fresh_b.txt", ["fresh source beta", "second chunk"]),
    ]
    factory = make_update_manifest_factory(fresh)

    with mock_embedding(embed_dim=8):
        result = migration.migrate(
            "c1",
            collections_path=str(base),
            from_source=True,
            manifest_factory=factory,
        )

    assert result.from_source is True
    assert result.number_of_documents == 2  # from the live source, not the 1 stored
    manifest = json.loads((base / "c1" / "manifest.json").read_text())
    assert manifest["version"] == "2"
    assert manifest["numberOfDocuments"] == 2
    docstore = json.loads((base / "c1" / "storage" / "docstore.json").read_text())
    node_ids = set(docstore["docstore/data"].keys())
    assert any(nid.startswith("fresh_a.txt") for nid in node_ids)
    assert not any(nid.startswith("stored.txt") for nid in node_ids)
