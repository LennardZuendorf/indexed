"""Unit tests for the v2 manifest model (core-v2/2a).

Covers plan.md scenarios: documented key order + version marker, round-trip
byte-stability, and the create-time factory recording the installed
llama-index-core/indexed-sh versions plus v1's embedding model / store /
score-kind defaults.
"""

from __future__ import annotations

import json
from importlib.metadata import version as pkg_version

import pytest
from pydantic import ValidationError

from indexed.protocols.models import ReaderDetails

pytestmark = pytest.mark.unit


def _reader() -> ReaderDetails:
    return ReaderDetails(type="localFiles", basePath="/tmp/docs")


def _new_manifest(**overrides):
    from indexed.core.v2.manifest import V2Manifest

    kwargs = dict(
        collection_name="demo",
        reader=_reader(),
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        created_time="2026-01-01T00:00:00Z",
        updated_time="2026-01-01T00:00:00Z",
        last_modified_document_time="2026-01-01T00:00:00Z",
    )
    kwargs.update(overrides)
    return V2Manifest.new(**kwargs)


def test_to_disk_key_order_and_version() -> None:
    disk = _new_manifest().to_disk()
    assert list(disk.keys()) == [
        "version",
        "collectionName",
        "createdTime",
        "updatedTime",
        "lastModifiedDocumentTime",
        "numberOfDocuments",
        "numberOfChunks",
        "reader",
        "engine",
    ]
    assert disk["version"] == "2"
    assert list(disk["engine"].keys()) == [
        "embedding",
        "vectorStore",
        "scoreKind",
        "llamaIndexCoreVersion",
        "indexedVersion",
    ]


def test_round_trip_from_disk_to_disk_is_byte_stable() -> None:
    from indexed.core.v2.manifest import V2Manifest

    raw = _new_manifest(number_of_documents=3, number_of_chunks=9).to_disk()
    round_tripped = V2Manifest.from_disk(raw).to_disk()
    assert json.dumps(round_tripped) == json.dumps(raw)


def test_created_time_absent_when_none() -> None:
    from indexed.core.v2.manifest import V2EmbeddingInfo, V2EngineBlock, V2Manifest

    manifest = V2Manifest(
        collection_name="demo",
        updated_time="t",
        last_modified_document_time="t",
        number_of_documents=0,
        number_of_chunks=0,
        reader=_reader(),
        engine=V2EngineBlock(
            embedding=V2EmbeddingInfo(provider="local", model="m", dimension=1),
            vector_store="simple",
            score_kind="cosine",
            llama_index_core_version="0.0.0",
            indexed_version="0.0.0",
        ),
    )
    assert "createdTime" not in manifest.to_disk()


def test_factory_defaults_match_v1_model_and_engine_block() -> None:
    manifest = _new_manifest()
    assert manifest.engine.embedding.provider == "local"
    assert manifest.engine.embedding.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert manifest.engine.embedding.dimension == 384
    assert manifest.engine.vector_store == "simple"
    assert manifest.engine.score_kind == "cosine"


def test_factory_records_installed_package_versions() -> None:
    manifest = _new_manifest()
    assert manifest.engine.llama_index_core_version == pkg_version("llama-index-core")
    assert manifest.engine.indexed_version == pkg_version("indexed-sh")


def test_from_disk_rejects_unsupported_version() -> None:
    from indexed.core.v2.manifest import V2Manifest

    raw = _new_manifest().to_disk()
    raw["version"] = "3"
    with pytest.raises(ValidationError):
        V2Manifest.from_disk(raw)


def test_package_version_helper_falls_back_to_unknown() -> None:
    from indexed.core.v2.manifest import _package_version

    assert _package_version("this-package-does-not-exist-xyz") == "unknown"
