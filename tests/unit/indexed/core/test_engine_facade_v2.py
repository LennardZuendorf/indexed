"""Facade v2 wiring + per-engine grouping (core-v2/2c).

- ``_engine_impl("2")`` resolves the real v2 services module.
- ``create --engine v2`` builds a v2 collection; ``search``/``status``/``inspect``
  on a detected-v2 collection route to v2 and coerce its field-keyed dicts into
  the shared ``CollectionStatus``/``CollectionInfo`` dataclasses.
- LIST-ALL / mixed ops handle a MIX of v1 and v2 collections: status/inspect
  concatenate per-engine, search merges the per-collection result dicts (R2).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

import pytest

from indexed.protocols import SourceConfig

from tests.conftest import model_available


# --- lightweight fakes (facade tests can't use the v2-dir conftest) ----------


def _doc(
    doc_id: str, chunks: List[str], modified: str = "2026-01-10T00:00:00+00:00"
) -> dict:
    return {
        "id": doc_id,
        "url": f"u/{doc_id}",
        "modifiedTime": modified,
        "text": " ".join(chunks),
        "chunks": [{"indexedData": c} for c in chunks],
    }


class _FakeConnector:
    def __init__(self, docs: List[dict]) -> None:
        outer = self

        class _R:
            def read_all_documents(self):
                yield from outer._docs

            def get_reader_details(self):
                return {"type": "localFiles", "basePath": "/corpus"}

        class _C:
            def convert(self, doc):
                return [doc]

        self._docs = docs
        self.reader = _R()
        self.converter = _C()


@contextmanager
def _mock_embed(embed_dim: int = 8) -> Iterator[None]:
    from unittest.mock import patch

    from llama_index.core.embeddings import MockEmbedding

    with patch(
        "indexed.core.v2.embedding.local.build_embed_model",
        return_value=MockEmbedding(embed_dim=embed_dim),
    ):
        yield


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")


def _facade_create_v2(cols: Path, name: str, docs: List[dict]) -> None:
    import indexed.core.engine as facade

    with _mock_embed():
        facade.create(
            [_cfg(name)],
            engine="2",
            use_cache=False,
            connector_factory=lambda cfg: _FakeConnector(list(docs)),
            collections_path=str(cols),
        )


# --- wiring -------------------------------------------------------------------


def test_engine_impl_two_resolves_v2_services() -> None:
    import indexed.core.engine as facade
    import indexed.core.v2.services as v2_services

    assert facade._engine_impl("2") is v2_services


def test_create_engine_two_builds_detectable_v2_collection(tmp_path: Path) -> None:
    from indexed.core.versioning import detect_engine_version

    cols = tmp_path / "cols"
    _facade_create_v2(cols, "c1", [_doc("d1", ["penguin migration"])])

    assert (cols / "c1" / "manifest.json").is_file()
    assert detect_engine_version(cols / "c1") == "2"


def test_status_on_v2_collection_returns_dataclass_via_facade(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.v1.engine.services import CollectionStatus

    cols = tmp_path / "cols"
    _facade_create_v2(cols, "c1", [_doc("d1", ["a", "b"]), _doc("d2", ["c"])])

    statuses = facade.status(collections_path=str(cols))
    assert len(statuses) == 1
    assert isinstance(statuses[0], CollectionStatus)
    assert statuses[0].name == "c1"
    assert statuses[0].number_of_chunks == 3


def test_inspect_on_v2_collection_returns_dataclass_via_facade(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.v1.engine.services import CollectionInfo

    cols = tmp_path / "cols"
    _facade_create_v2(cols, "c1", [_doc("d1", ["a", "b"]), _doc("d2", ["c"])])

    infos = facade.inspect(collections_path=str(cols))
    assert len(infos) == 1
    assert isinstance(infos[0], CollectionInfo)
    assert infos[0].avg_chunks_per_doc == pytest.approx(1.5)


def test_search_on_v2_collection_routes_via_facade(tmp_path: Path) -> None:
    import indexed.core.engine as facade

    cols = tmp_path / "cols"
    _facade_create_v2(cols, "c1", [_doc("d1", ["penguin migration"])])

    with _mock_embed():
        res = facade.search("penguin", configs=[_cfg("c1")], collections_path=str(cols))
    assert set(res.keys()) == {"c1"}
    assert "error" not in res["c1"]


def test_search_rerank_reaches_v2_and_overrides_disabled_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``facade.search(..., rerank=True)`` on a v2 collection overrides the
    default-disabled ``[core.v2.rerank]`` for that one call (core-v2-
    discoverability/2, R2) — proven end to end via the ``scoreKind: rerank``
    marker retrieval.py only sets once a rerank actually ran. ``_apply_rerank``
    is stubbed to identity so no real cross-encoder is loaded."""
    import indexed.core.engine as facade
    from indexed.core.v2 import retrieval

    monkeypatch.setattr(retrieval, "_apply_rerank", lambda nws, q, cfg: nws)

    cols = tmp_path / "cols"
    _facade_create_v2(cols, "c1", [_doc("d1", ["penguin migration"])])

    with _mock_embed():
        res = facade.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            rerank=True,
        )
    assert res["c1"]["scoreKind"] == "rerank"


def test_update_on_v2_collection_routes_via_facade(tmp_path: Path) -> None:
    """The facade resolves the collection's engine from its manifest (R2) and
    routes ``update`` to the v2 incremental path — a new doc becomes searchable."""
    import json

    import indexed.core.engine as facade
    from indexed.protocols.connectors import ConnectorRun

    cols = tmp_path / "cols"
    _facade_create_v2(cols, "c1", [_doc("d1", ["penguin migration antarctic"])])

    def _manifest_factory(manifest, storage_path):  # noqa: ANN001
        # Rebuild a ConnectorRun yielding the new doc (as the files connector's
        # from_manifest would for a changed corpus).
        class _R:
            def read_all_documents(self):
                yield _doc("d2", ["volcanic soil sulfur caldera"])

            def get_reader_details(self):
                return {"type": "localFiles", "basePath": "/corpus"}

        class _C:
            def convert(self, doc):
                return [doc]

        return ConnectorRun(_R(), _C(), [], None)

    with _mock_embed():
        facade.update(
            [_cfg("c1")], collections_path=str(cols), manifest_factory=_manifest_factory
        )

    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["numberOfDocuments"] == 2

    with _mock_embed():
        res = facade.search(
            "volcanic soil", configs=[_cfg("c1")], collections_path=str(cols)
        )
    assert {r["id"] for r in res["c1"]["results"]} == {"d1", "d2"}


def test_clear_on_v2_collection_via_facade(tmp_path: Path) -> None:
    import indexed.core.engine as facade

    cols = tmp_path / "cols"
    _facade_create_v2(cols, "c1", [_doc("d1", ["penguin"])])
    assert (cols / "c1").is_dir()
    facade.clear(["c1"], collections_path=str(cols))
    assert not (cols / "c1").exists()


# --- mixed v1 + v2 (§5b — model-gated: the v1 side runs real embeddings) ------


@pytest.mark.skipif(
    not model_available(), reason="Embedding model not cached (all-MiniLM-L6-v2)"
)
def test_mixed_v1_v2_status_lists_both(
    tmp_path: Path, files_corpus: Path, build_collection
) -> None:
    import indexed.core.engine as facade
    from indexed.connectors.files.connector import FileSystemConnector

    cols = tmp_path / "cols"
    cols.mkdir()
    # v1 collection (real FAISS + embeddings via the shared build_collection net).
    conn = FileSystemConnector(path=str(files_corpus))
    build_collection(cols, "v1-coll", conn.reader, conn.converter)
    # v2 collection (real model too).
    facade.create(
        [
            SourceConfig(
                name="v2-coll", type="localFiles", base_url_or_path=str(files_corpus)
            )
        ],
        engine="2",
        use_cache=False,
        connector_factory=lambda cfg: FileSystemConnector(path=str(files_corpus)),
        collections_path=str(cols),
    )

    statuses = facade.status(collections_path=str(cols))
    names = sorted(s.name for s in statuses)
    assert names == ["v1-coll", "v2-coll"]


@pytest.mark.skipif(
    not model_available(), reason="Embedding model not cached (all-MiniLM-L6-v2)"
)
def test_mixed_v1_v2_search_returns_both_under_their_keys(
    tmp_path: Path, files_corpus: Path, build_collection
) -> None:
    import indexed.core.engine as facade
    from indexed.connectors.files.connector import FileSystemConnector

    cols = tmp_path / "cols"
    cols.mkdir()
    conn = FileSystemConnector(path=str(files_corpus))
    build_collection(cols, "v1-coll", conn.reader, conn.converter)
    facade.create(
        [
            SourceConfig(
                name="v2-coll", type="localFiles", base_url_or_path=str(files_corpus)
            )
        ],
        engine="2",
        use_cache=False,
        connector_factory=lambda cfg: FileSystemConnector(path=str(files_corpus)),
        collections_path=str(cols),
    )

    # configs=None spans both engines; each collection's results stay under its
    # own key in its engine's native score units (no cross-engine re-rank here).
    res = facade.search(
        "penguin migration antarctic",
        collections_path=str(cols),
        include_matched_chunks=True,
    )
    assert set(res.keys()) == {"v1-coll", "v2-coll"}
    for name in ("v1-coll", "v2-coll"):
        assert "error" not in res[name], res[name]
        assert res[name]["results"], f"{name} should have hits"
        assert res[name]["results"][0]["id"] == "needle.txt"
