"""Facade ``engine_descriptors`` — R13 engine identity (core-v2/2d).

``engine_descriptors`` reads only ``manifest.json`` (no index load, no model),
so these are fully model-free: synthetic v1/v2 collection dirs on disk. It routes
engine info THROUGH the facade (a new ``EngineDescriptor`` dataclass), so the CLI
never imports ``core.v2`` for R13 display.
"""

from __future__ import annotations

import json
from pathlib import Path

from indexed.core.engine import EngineDescriptor, engine_descriptors


def _write_v2(
    base: Path,
    name: str,
    *,
    model: str = "sentence-transformers/all-MiniLM-L6-v2",
    store: str = "simple",
    provider: str = "local",
) -> None:
    d = base / name
    d.mkdir(parents=True)
    manifest = {
        "version": "2",
        "collectionName": name,
        "createdTime": "t",
        "updatedTime": "t",
        "lastModifiedDocumentTime": "t",
        "numberOfDocuments": 1,
        "numberOfChunks": 2,
        "reader": {"type": "localFiles"},
        "engine": {
            "embedding": {"provider": provider, "model": model, "dimension": 384},
            "vectorStore": store,
            "scoreKind": "cosine",
            "llamaIndexCoreVersion": "0.14.23",
            "indexedVersion": "0.0.5",
        },
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_v1(base: Path, name: str, *, indexer: str = "all-MiniLM-L6-v2") -> None:
    d = base / name
    d.mkdir(parents=True)
    manifest = {
        "collectionName": name,
        "updatedTime": "t",
        "lastModifiedDocumentTime": "t",
        "numberOfDocuments": 1,
        "numberOfChunks": 2,
        "reader": {"type": "localFiles"},
        "indexers": [{"name": indexer}],
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_v2_descriptor_reports_engine_model_store(tmp_path: Path) -> None:
    _write_v2(tmp_path, "v2c")
    (desc,) = engine_descriptors(["v2c"], collections_path=str(tmp_path))
    assert isinstance(desc, EngineDescriptor)
    assert desc.name == "v2c"
    assert desc.engine_version == "2"
    assert desc.embedding_provider == "local"
    assert desc.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert desc.vector_store == "simple"


def test_v1_descriptor_reports_engine_one(tmp_path: Path) -> None:
    _write_v1(tmp_path, "v1c", indexer="indexer_all-MiniLM-L6-v2")
    (desc,) = engine_descriptors(["v1c"], collections_path=str(tmp_path))
    assert desc.engine_version == "1"
    assert desc.embedding_model == "indexer_all-MiniLM-L6-v2"
    assert desc.embedding_provider is None
    assert desc.vector_store == "faiss"


def test_mixed_collections_list_both_engines(tmp_path: Path) -> None:
    _write_v1(tmp_path, "v1c")
    _write_v2(tmp_path, "v2c")
    by_name = {d.name: d for d in engine_descriptors(collections_path=str(tmp_path))}
    assert set(by_name) == {"v1c", "v2c"}
    assert by_name["v1c"].engine_version == "1"
    assert by_name["v2c"].engine_version == "2"


def test_missing_manifest_is_omitted(tmp_path: Path) -> None:
    (tmp_path / "ghost").mkdir()  # dir, no manifest.json
    assert engine_descriptors(["ghost"], collections_path=str(tmp_path)) == []


def test_corrupt_manifest_is_omitted(tmp_path: Path) -> None:
    d = tmp_path / "broken"
    d.mkdir()
    (d / "manifest.json").write_text("{ not valid json", encoding="utf-8")
    assert engine_descriptors(["broken"], collections_path=str(tmp_path)) == []


def test_unknown_version_marker_is_omitted_not_raised(tmp_path: Path) -> None:
    d = tmp_path / "future"
    d.mkdir()
    (d / "manifest.json").write_text(
        json.dumps({"version": "3", "collectionName": "future"}), encoding="utf-8"
    )
    # Display helper never fails loud — the operational ops enforce R1.
    assert engine_descriptors(["future"], collections_path=str(tmp_path)) == []
