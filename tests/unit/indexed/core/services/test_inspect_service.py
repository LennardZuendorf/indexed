"""Tests for InspectService reporting correctness (foundation/6e F1-F3).

Builds fake collection directories on disk (manifest + documents + a FAISS
index file) so these run fast without the embedding model, unlike the
characterization specs in ``tests/characterization/test_known_bugs.py``
which exercise the same bugs end-to-end through the real engine.
"""

import json
import sys
from pathlib import Path

import pytest

from indexed.config.errors import StorageError
from indexed.core.v1.engine.services.inspect_service import InspectService

INDEXER_NAME = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


def _write_collection(
    root: Path,
    name: str,
    *,
    manifest: dict,
    documents: dict[str, bytes] | None = None,
    index_bytes: bytes | None = None,
) -> None:
    """Create a minimal on-disk collection: manifest + documents + index."""
    coll_dir = root / name
    coll_dir.mkdir(parents=True)
    (coll_dir / "manifest.json").write_text(json.dumps(manifest))

    if documents:
        docs_dir = coll_dir / "documents"
        docs_dir.mkdir()
        for filename, content in documents.items():
            (docs_dir / filename).write_bytes(content)

    if index_bytes is not None:
        indexer_name = manifest["indexers"][0]["name"]
        index_dir = coll_dir / "indexes" / indexer_name
        index_dir.mkdir(parents=True)
        (index_dir / "indexer.faiss").write_bytes(index_bytes)


class TestF1IndexSizeBytes:
    """F1: index_size_bytes must be a real file byte size, not ntotal."""

    def test_index_size_bytes_is_real_file_size(self, tmp_path):
        # numberOfChunks (5) deliberately does NOT match the fake index
        # file's byte size (5000) — the old bug reported the chunk/vector
        # count formatted as if it were bytes.
        _write_collection(
            tmp_path,
            "coll",
            manifest={
                "collectionName": "coll",
                "numberOfDocuments": 2,
                "numberOfChunks": 5,
                "indexers": [{"name": INDEXER_NAME}],
            },
            documents={"a.json": b"x" * 10, "b.json": b"y" * 20},
            index_bytes=b"\x00" * 5000,
        )

        info = InspectService(collections_path=str(tmp_path)).inspect(
            ["coll"], include_index_size=True
        )[0]

        assert info.index_size_bytes == 5000
        assert info.index_size_bytes != info.number_of_chunks

    def test_index_size_bytes_none_when_missing(self, tmp_path):
        """A collection with no index file on disk must not crash — None."""
        _write_collection(
            tmp_path,
            "coll",
            manifest={
                "collectionName": "coll",
                "numberOfDocuments": 1,
                "numberOfChunks": 1,
                "indexers": [{"name": INDEXER_NAME}],
            },
            documents={"a.json": b"x" * 10},
        )

        info = InspectService(collections_path=str(tmp_path)).inspect(
            ["coll"], include_index_size=True
        )[0]

        assert info.index_size_bytes is None


class TestF2CreatedTime:
    """F2: created_time is read from the manifest, tolerating its absence."""

    def test_created_time_present(self, tmp_path):
        _write_collection(
            tmp_path,
            "coll",
            manifest={
                "collectionName": "coll",
                "createdTime": "2026-01-01T00:00:00+00:00",
                "numberOfDocuments": 1,
                "numberOfChunks": 1,
                "indexers": [{"name": INDEXER_NAME}],
            },
            documents={"a.json": b"x" * 10},
        )

        info = InspectService(collections_path=str(tmp_path)).inspect(["coll"])[0]

        assert info.created_time == "2026-01-01T00:00:00+00:00"

    def test_created_time_none_on_legacy_manifest_without_key(self, tmp_path):
        """A collection created before F2 has no ``createdTime`` key at all —
        it must still load and inspect cleanly, reporting None (on-disk
        compat: additive key, never required)."""
        _write_collection(
            tmp_path,
            "coll",
            manifest={
                "collectionName": "coll",
                "updatedTime": "2026-01-01T00:00:00+00:00",
                "numberOfDocuments": 1,
                "numberOfChunks": 1,
                "indexers": [{"name": INDEXER_NAME}],
            },
            documents={"a.json": b"x" * 10},
        )

        info = InspectService(collections_path=str(tmp_path)).inspect(["coll"])[0]

        assert info.created_time is None


class TestF3AvgDocSizeExcludesIndex:
    """F3: avg_doc_size_bytes must be computed from document bytes only."""

    def test_avg_doc_size_excludes_index_and_manifest(self, tmp_path):
        _write_collection(
            tmp_path,
            "coll",
            manifest={
                "collectionName": "coll",
                "numberOfDocuments": 2,
                "numberOfChunks": 4,
                "indexers": [{"name": INDEXER_NAME}],
            },
            documents={"a.json": b"a" * 100, "b.json": b"b" * 200},
            index_bytes=b"\x00" * 10_000,
        )

        info = InspectService(collections_path=str(tmp_path)).inspect(
            ["coll"], include_index_size=True
        )[0]

        # (100 + 200) / 2 documents = 150 bytes/doc — independent of the
        # 10,000-byte index file and the manifest.json overhead.
        assert info.avg_doc_size_bytes == 150.0
        assert info.disk_size_bytes is not None
        assert info.avg_doc_size_bytes * info.number_of_documents < info.disk_size_bytes

    def test_avg_doc_size_none_when_no_documents(self, tmp_path):
        _write_collection(
            tmp_path,
            "coll",
            manifest={
                "collectionName": "coll",
                "numberOfDocuments": 0,
                "numberOfChunks": 0,
                "indexers": [{"name": INDEXER_NAME}],
            },
        )

        info = InspectService(collections_path=str(tmp_path)).inspect(["coll"])[0]

        assert info.avg_doc_size_bytes is None


class TestDiscoveryFiltersInternalDirs:
    """Build-aside staging / swap-rollback dirs must never surface as collections."""

    def test_status_omits_tmp_and_trash_dirs(self, tmp_path):
        base = {
            "updatedTime": "2026-07-07T00:00:00+00:00",
            "lastModifiedDocumentTime": "2026-07-07T00:00:00+00:00",
            "numberOfDocuments": 1,
            "numberOfChunks": 1,
            "reader": {"type": "localFiles"},
            "indexers": [{"name": "idx"}],
        }
        _write_collection(tmp_path, "docs", manifest={"collectionName": "docs", **base})
        # A staging dir from an interrupted durable create, and a trash dir from
        # a failed swap-rollback cleanup — each holds a valid manifest but is an
        # internal artifact, not a real collection.
        _write_collection(
            tmp_path,
            "docs.tmp-12345-abcd1234",
            manifest={"collectionName": "docs.tmp-12345-abcd1234", **base},
        )
        _write_collection(
            tmp_path,
            "docs.trash-12345",
            manifest={"collectionName": "docs.trash-12345", **base},
        )

        names = {
            s.name for s in InspectService(collections_path=str(tmp_path)).status()
        }
        assert names == {"docs"}


class TestDiscoverCollectionsFailsLoud:
    """Bug 2: a directory-scan I/O error must fail loud, not silently return
    zero collections (tech.md "fail loud, never zero-filled"). Per-collection
    manifest errors (status()/inspect() lines ~242-248) stay tolerated —
    only the top-level scan swallow is the bug."""

    def test_discover_collections_raises_and_logs_on_scan_error(self, capsys):
        from loguru import logger as loguru_logger

        # inspect_service logs via loguru (not stdlib logging), so assert on
        # its default stderr sink rather than caplog (which only hooks stdlib
        # logging and would otherwise silently observe nothing).
        loguru_logger.remove()
        loguru_logger.add(sys.stderr, level="ERROR")
        try:
            service = InspectService(collections_path="/nonexistent-for-test")
            service._persister.read_folder_files = lambda *_a, **_kw: (
                _ for _ in ()
            ).throw(OSError("permission denied"))

            with pytest.raises(StorageError, match="permission denied"):
                service._discover_collections()
        finally:
            loguru_logger.remove()

        stderr = capsys.readouterr().err
        assert "Error scanning collections directory" in stderr
        assert "permission denied" in stderr

    def test_status_propagates_scan_error_instead_of_empty_list(self, tmp_path):
        """The default status()/inspect() path (collection_names=None) must
        not swallow a scan error into an empty (fake-healthy) result."""
        service = InspectService(collections_path=str(tmp_path))
        service._persister.read_folder_files = lambda *_a, **_kw: (_ for _ in ()).throw(
            OSError("permission denied")
        )

        with pytest.raises(StorageError):
            service.status()

    def test_discover_collections_returns_empty_on_missing_dir(self, tmp_path):
        """R3: a fresh install with no collections directory yet must not
        crash ``indexed inspect``/``indexed index search`` — a missing top
        dir (ENOENT) is a normal, empty state, not a scan failure."""
        service = InspectService(collections_path=str(tmp_path / "does-not-exist"))

        assert service._discover_collections() == []


class TestMissingManifestLogLevel:
    """UX finding L3: a missing collection is the expected, common
    "not found" case — its manifest-read failure must not log at ERROR
    (redundant noise above the friendly "not found" panel). Genuine read
    errors (corrupt/undecodable manifest, permission failures, etc.) are
    real problems and must stay at ERROR so operators still see them.

    inspect_service logs via loguru (not stdlib logging), so assert on its
    stderr sink rather than caplog — same pattern as
    TestDiscoverCollectionsFailsLoud above.
    """

    def test_status_missing_collection_does_not_log_error(self, tmp_path, capsys):
        from loguru import logger as loguru_logger

        loguru_logger.remove()
        loguru_logger.add(sys.stderr, level="ERROR")
        try:
            statuses = InspectService(collections_path=str(tmp_path)).status(
                ["does-not-exist"]
            )
        finally:
            loguru_logger.remove()

        # Friendly behavior unchanged: missing collection is simply omitted.
        assert statuses == []
        stderr = capsys.readouterr().err
        assert "ERROR" not in stderr

    def test_status_genuine_read_error_still_logs_error(self, tmp_path, capsys):
        from loguru import logger as loguru_logger

        # The collection dir exists but its manifest is corrupt — a real
        # failure, distinct from "collection doesn't exist at all".
        coll_dir = tmp_path / "broken"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{not valid json")

        loguru_logger.remove()
        loguru_logger.add(sys.stderr, level="ERROR")
        try:
            statuses = InspectService(collections_path=str(tmp_path)).status(["broken"])
        finally:
            loguru_logger.remove()

        assert statuses == []
        stderr = capsys.readouterr().err
        assert "ERROR" in stderr
        assert "Error getting status for collection broken" in stderr

    def test_inspect_missing_collection_does_not_log_error(self, tmp_path, capsys):
        from loguru import logger as loguru_logger

        loguru_logger.remove()
        loguru_logger.add(sys.stderr, level="ERROR")
        try:
            infos = InspectService(collections_path=str(tmp_path)).inspect(
                ["does-not-exist"]
            )
        finally:
            loguru_logger.remove()

        assert infos == []
        stderr = capsys.readouterr().err
        assert "ERROR" not in stderr

    def test_inspect_genuine_read_error_still_logs_error(self, tmp_path, capsys):
        from loguru import logger as loguru_logger

        coll_dir = tmp_path / "broken"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{not valid json")

        loguru_logger.remove()
        loguru_logger.add(sys.stderr, level="ERROR")
        try:
            infos = InspectService(collections_path=str(tmp_path)).inspect(["broken"])
        finally:
            loguru_logger.remove()

        assert infos == []
        stderr = capsys.readouterr().err
        assert "ERROR" in stderr
        assert "Error inspecting collection broken" in stderr
