"""v2 engine service-surface tests (core-v2/2c ``core.v2.services``).

Covers the 7-name contract the facade calls: create/search delegate; status/
inspect return field-keyed dicts that build the shared v1 dataclasses; clear/
collection_exists are filesystem ops; update delegates to the incremental
ingestion path (wrapping upstream errors at the boundary).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from indexed.core.v2 import services
from indexed.protocols import SourceConfig

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")


def _build(cols: Path, name: str, docs) -> None:
    with mock_embedding(embed_dim=8):
        services.create(
            [_cfg(name)],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )


def test_service_surface_exposes_seven_names() -> None:
    for name in (
        "create",
        "update",
        "clear",
        "collection_exists",
        "search",
        "status",
        "inspect",
    ):
        assert callable(getattr(services, name))


def test_create_empty_corpus_error_passes_through_unprefixed(tmp_path: Path) -> None:
    """The service boundary's ``_wrap`` passes typed ``IndexedError``s through
    unchanged (core-v2/2c review Finding 3): ingestion's empty-corpus
    ``CoreV2Error`` must keep its own actionable message, NOT get rewrapped
    with the generic ``"v2 create failed: ..."`` prefix that would otherwise
    obscure a user-actionable condition.
    """
    from indexed.core.errors import CoreV2Error

    cols = tmp_path / "cols"
    with mock_embedding(embed_dim=8):
        with pytest.raises(CoreV2Error) as excinfo:
            services.create(
                [_cfg("empty")],
                use_cache=False,
                connector_factory=make_connector_factory([]),
                collections_path=str(cols),
            )
    message = str(excinfo.value)
    assert "No documents found for collection 'empty'" in message
    assert "v2 create failed" not in message


def test_update_delegates_to_incremental_ingestion(tmp_path: Path) -> None:
    """The service ``update`` routes to the real incremental path: a new doc is
    added, an unchanged doc is skipped (re-embed count proven by the record)."""
    from tests.unit.indexed.core.v2._engine_helpers import (
        make_update_manifest_factory,
        recording_embedding,
    )

    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("a", ["alpha one"])])

    with recording_embedding(embed_dim=8) as embedded:
        services.update(
            [_cfg("c1")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory(
                [make_doc("a", ["alpha one"]), make_doc("b", ["beta one"])]
            ),
        )
    # Only the new doc ``b`` was embedded; unchanged ``a`` was skipped.
    assert len(embedded) == 1
    assert any("beta one" in t for t in embedded)

    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["numberOfDocuments"] == 2


def test_update_wraps_upstream_errors_as_core_v2_error(tmp_path: Path) -> None:
    """A non-``IndexedError`` failure inside update is wrapped at the boundary."""
    from indexed.core.errors import CoreV2Error

    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("a", ["alpha one"])])

    def _bad_factory(manifest, storage_path):  # noqa: ANN001
        raise RuntimeError("connector rebuild exploded")

    with pytest.raises(CoreV2Error, match="v2 update failed"):
        services.update(
            [_cfg("c1")], collections_path=str(cols), manifest_factory=_bad_factory
        )


def test_collection_exists_true_and_false(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])
    assert services.collection_exists("c1", collections_path=str(cols)) is True
    assert services.collection_exists("nope", collections_path=str(cols)) is False


def test_clear_removes_collection_dir(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])
    assert (cols / "c1").is_dir()
    services.clear(["c1"], collections_path=str(cols))
    assert not (cols / "c1").exists()


def test_status_dicts_build_collection_status(tmp_path: Path) -> None:
    from indexed.core.v1.engine.services import CollectionStatus

    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["a", "b"]), make_doc("d2", ["c"])])

    dicts = services.status(collections_path=str(cols))
    assert len(dicts) == 1
    d = dicts[0]
    assert d["name"] == "c1"
    assert d["number_of_documents"] == 2
    assert d["number_of_chunks"] == 3
    assert d["source_type"] == "localFiles"
    # The facade builds the shared dataclass from exactly these keys.
    status = CollectionStatus(**d)
    assert status.name == "c1"
    assert status.number_of_chunks == 3


def test_inspect_dicts_build_collection_info(tmp_path: Path) -> None:
    from indexed.core.v1.engine.services import CollectionInfo

    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["a", "b"]), make_doc("d2", ["c"])])

    dicts = services.inspect(collections_path=str(cols))
    assert len(dicts) == 1
    info = CollectionInfo(**dicts[0])
    assert info.name == "c1"
    assert info.number_of_documents == 2
    assert info.number_of_chunks == 3
    assert info.avg_chunks_per_doc == pytest.approx(1.5)
    assert info.source_type == "localFiles"


def test_status_omits_unreadable_collection(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    corrupt = cols / "broken"
    corrupt.mkdir(parents=True)
    (corrupt / "manifest.json").write_text("{ not json", encoding="utf-8")

    # Explicitly asking for it: omitted (not zero-filled, not raised).
    assert services.status(["broken"], collections_path=str(cols)) == []


def test_status_discovers_only_v2_collections(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["x"])])
    # A v1-style manifest (no version) alongside must NOT be reported by v2.
    v1_dir = cols / "legacy"
    v1_dir.mkdir()
    (v1_dir / "manifest.json").write_text(
        '{"collectionName": "legacy", "numberOfDocuments": 1}', encoding="utf-8"
    )

    names = [d["name"] for d in services.status(collections_path=str(cols))]
    assert names == ["c1"]
