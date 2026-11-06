"""v2 SEARCH path tests (core-v2/2c ``retrieval.search``).

Result-shape, threshold, discovery, per-collection error handling and the
Settings-untouched proof are MODEL-FREE (MockEmbedding). The KNOWN-HIT relevance
test gates on ``model_available()`` and uses the real corpus + model.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from indexed.core.v2 import ingestion, retrieval
from indexed.core.v2.config_models import CoreV2RerankConfig
from indexed.protocols import SourceConfig

from tests.conftest import model_available

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)

pytestmark = pytest.mark.unit


def _cross_encoder_cached() -> bool:
    """True when the default cross-encoder rerank model is already cached.

    Mirrors ``model_available()`` for the embedding model — enabling rerank the
    first time downloads the CE model (opt-in), so real-CE tests gate on this.
    """
    from indexed.core.v2.embedding.local import _is_model_cached

    return _is_model_cached("cross-encoder/ms-marco-MiniLM-L-6-v2")


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="")


def _build(cols: Path, name: str, docs) -> None:
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )


def test_search_returns_v1_result_shape(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    docs = [make_doc("d1", ["penguin migration", "second chunk"])]
    _build(cols, "c1", docs)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_matched_chunks=True,
        )

    assert set(res.keys()) == {"c1"}
    per = res["c1"]
    assert per["collectionName"] == "c1"
    assert "indexerName" in per
    assert "error" not in per
    doc = per["results"][0]
    assert doc["id"] == "d1"
    assert "url" in doc and "path" in doc
    chunk = doc["matchedChunks"][0]
    assert set(chunk) == {"chunkNumber", "score", "content"}
    assert isinstance(chunk["score"], float)
    assert chunk["content"] == {"indexedData": "penguin migration"}


def test_search_omits_content_when_not_requested(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )
    chunk = res["c1"]["results"][0]["matchedChunks"][0]
    assert "content" not in chunk


def test_full_text_and_all_chunks_absent_by_default(tmp_path: Path) -> None:
    """R4 parity: neither field appears unless explicitly requested (v1)."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration", "second chunk"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )
    doc = res["c1"]["results"][0]
    assert "text" not in doc
    assert "allChunks" not in doc


def test_include_full_text_attaches_reconstructed_text(tmp_path: Path) -> None:
    """``include_full_text`` reconstructs the document text from its chunk nodes
    (v2 keeps no ``documents/<id>.json``)."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration", "second chunk"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_full_text=True,
        )
    doc = res["c1"]["results"][0]
    assert doc["id"] == "d1"
    assert "penguin migration" in doc["text"]
    assert "second chunk" in doc["text"]


def test_include_all_chunks_returns_every_document_chunk(tmp_path: Path) -> None:
    """``include_all_chunks`` returns ALL of a matched doc's chunks (not only the
    matched ones), in order, in v1's ``{"indexedData": ...}`` shape."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration", "second chunk"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_all_chunks=True,
        )
    doc = res["c1"]["results"][0]
    all_chunks = doc["allChunks"]
    assert [c["indexedData"] for c in all_chunks] == [
        "penguin migration",
        "second chunk",
    ]
    # No original per-chunk metadata → v1's minimal on-disk shape (indexedData only).
    assert all(set(c) == {"indexedData"} for c in all_chunks)


def test_all_chunks_recovers_original_chunk_metadata(tmp_path: Path) -> None:
    """A chunk that carried its own metadata surfaces it in ``allChunks`` with the
    engine-owned keys (source_id/url/chunk_number/collection/modified_time)
    stripped — v1's on-disk ``{"indexedData", "metadata"}`` shape."""
    cols = tmp_path / "cols"
    doc = {
        "id": "d1",
        "url": "u",
        "modifiedTime": "2026-01-10T00:00:00+00:00",
        "text": "body",
        "chunks": [{"indexedData": "penguin", "metadata": {"heading": "Intro"}}],
    }
    _build(cols, "c1", [doc])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_all_chunks=True,
        )
    (chunk,) = res["c1"]["results"][0]["allChunks"]
    assert chunk["indexedData"] == "penguin"
    assert chunk["metadata"] == {"heading": "Intro"}  # engine keys stripped


def test_search_never_resolves_settings_llm(tmp_path: Path) -> None:
    """Retriever-only: the search path must NEVER read ``Settings.llm`` (no
    as_query_engine, no OpenAI-by-default trap). We install a property that
    raises on any access and assert the search still succeeds."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"])])

    from llama_index.core import Settings

    original = type(Settings).llm

    def _boom(self):  # noqa: ANN001, ANN202
        raise AssertionError("search resolved Settings.llm — must be retriever-only")

    type(Settings).llm = property(_boom)
    try:
        with mock_embedding(embed_dim=8):
            res = retrieval.search(
                "penguin", configs=[_cfg("c1")], collections_path=str(cols)
            )
    finally:
        type(Settings).llm = original

    assert res["c1"]["results"], "search should return hits without touching the LLM"


def test_score_threshold_filters_below_cutoff(tmp_path: Path) -> None:
    """v2 threshold keeps ``score >= threshold`` (cosine, higher-better).

    MockEmbedding yields identical vectors → cosine ≈ 1.0, so a 1.5 cutoff drops
    everything while a 0.5 cutoff keeps the hit."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])

    with mock_embedding(embed_dim=8):
        keep = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            score_threshold=0.5,
        )
        drop = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            score_threshold=1.5,
        )

    assert keep["c1"]["results"]
    assert drop["c1"]["results"] == []


def test_search_discovers_all_v2_collections_when_configs_none(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])
    _build(cols, "c2", [make_doc("d2", ["walrus"])])

    with mock_embedding(embed_dim=8):
        res = retrieval.search("anything", configs=None, collections_path=str(cols))

    assert set(res.keys()) == {"c1", "c2"}


def test_search_missing_collection_returns_error_entry_not_raise(
    tmp_path: Path,
) -> None:
    cols = tmp_path / "cols"
    cols.mkdir()
    with mock_embedding(embed_dim=8):
        res = retrieval.search("q", configs=[_cfg("ghost")], collections_path=str(cols))
    assert "error" in res["ghost"]


@pytest.mark.slow
@pytest.mark.skipif(
    not model_available(), reason="Embedding model not cached (all-MiniLM-L6-v2)"
)
def test_search_known_hit_with_real_model(tmp_path: Path, files_corpus: Path) -> None:
    """Real model + real files corpus: the needle doc is the top hit for its
    query, and a different query ranks a different doc first (not just 'no
    error')."""
    from indexed.connectors.files.connector import FileSystemConnector

    cols = tmp_path / "cols"
    ingestion.create(
        [
            SourceConfig(
                name="files-v2", type="localFiles", base_url_or_path=str(files_corpus)
            )
        ],
        use_cache=False,
        connector_factory=lambda cfg: FileSystemConnector(path=str(files_corpus)),
        collections_path=str(cols),
    )

    needle = retrieval.search(
        "penguin migration antarctic coastline",
        configs=[_cfg("files-v2")],
        collections_path=str(cols),
        include_matched_chunks=True,
    )
    ranked = [d["id"] for d in needle["files-v2"]["results"]]
    assert ranked, "expected at least one hit"
    assert ranked[0] == "needle.txt", ranked

    other = retrieval.search(
        "semantic search finds documents by meaning",
        configs=[_cfg("files-v2")],
        collections_path=str(cols),
    )
    other_ranked = [d["id"] for d in other["files-v2"]["results"]]
    assert other_ranked[0] != "needle.txt", other_ranked
    # v2 score is cosine, higher-is-better (0..1).
    top_score = needle["files-v2"]["results"][0]["matchedChunks"][0]["score"]
    assert 0.0 < top_score <= 1.0


# --- R10: optional reranking -------------------------------------------------


def test_rerank_disabled_imports_no_cross_encoder(tmp_path: Path) -> None:
    """Disabled (the default) → zero cost: the search must import NO
    ``sentence_transformers`` / ``CrossEncoder`` at all.

    An import guard fails the search if any ``sentence_transformers`` import is
    attempted during a rerank-disabled search (MockEmbedding, so nothing else
    would legitimately import it)."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"]), make_doc("d2", ["x"])])

    import builtins

    real_import = builtins.__import__

    def _guard(name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise AssertionError(f"rerank disabled must not import {name!r}")
        return real_import(name, *args, **kwargs)

    with mock_embedding(embed_dim=8):
        with patch("builtins.__import__", side_effect=_guard):
            res = retrieval.search(
                "penguin", configs=[_cfg("c1")], collections_path=str(cols)
            )
    assert res["c1"]["results"], "disabled-rerank search still returns hits"


def test_rerank_enabled_reorders_and_respects_top_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabled → the postprocessor is constructed with the configured model +
    ``top_n``, and its reordered/truncated node list drives the output (order
    changes, ``top_n`` respected). Deterministic via a FAKE reranker (no CE
    download), so this runs everywhere; the real-CE path is a gated test below.
    """
    cols = tmp_path / "cols"
    _build(
        cols,
        "c1",
        [
            make_doc("d1", ["alpha"]),
            make_doc("d2", ["beta"]),
            make_doc("d3", ["gamma"]),
        ],
    )

    with mock_embedding(embed_dim=8):
        baseline = retrieval.search(
            "alpha", configs=[_cfg("c1")], collections_path=str(cols)
        )
    baseline_ids = [d["id"] for d in baseline["c1"]["results"]]
    assert len(baseline_ids) == 3

    monkeypatch.setattr(
        "indexed.core.v2.retrieval.resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="test-ce", top_n=2),
    )

    import llama_index.core.postprocessor as pp

    class _FakeRerank:
        seen: dict = {}

        def __init__(self, *, model: str, top_n: int) -> None:
            _FakeRerank.seen = {"model": model, "top_n": top_n}
            self._top_n = top_n

        def postprocess_nodes(self, nodes, *, query_str=None, query_bundle=None):  # noqa: ANN001, ANN002, ANN003, ANN202
            # Reverse (so order provably changes) and truncate to top_n.
            return list(reversed(nodes))[: self._top_n]

    monkeypatch.setattr(pp, "SentenceTransformerRerank", _FakeRerank)

    with mock_embedding(embed_dim=8):
        reranked = retrieval.search(
            "alpha", configs=[_cfg("c1")], collections_path=str(cols)
        )
    reranked_ids = [d["id"] for d in reranked["c1"]["results"]]

    assert _FakeRerank.seen == {"model": "test-ce", "top_n": 2}
    assert len(reranked_ids) == 2  # top_n respected
    assert reranked_ids == list(reversed(baseline_ids))[:2]  # order changed


@pytest.mark.unit
def test_reranked_response_uses_rerank_score_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabled rerank REPLACES ``NodeWithScore.score`` with a cross-encoder
    relevance, so the response must report ``scoreKind == "rerank"`` — not the
    manifest's ``"cosine"`` — or downstream mixed-engine sorting mislabels the
    scores (PR #158 review #8). ``_apply_rerank`` is stubbed to identity so no
    real cross-encoder loads."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"])])

    monkeypatch.setattr(
        retrieval,
        "resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="x", top_n=3),
    )
    monkeypatch.setattr(retrieval, "_apply_rerank", lambda nws, q, cfg: nws)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )

    assert res["c1"]["scoreKind"] == "rerank"


@pytest.mark.slow
@pytest.mark.skipif(
    not (model_available() and _cross_encoder_cached()),
    reason="embedding or cross-encoder model not cached",
)
def test_rerank_enabled_real_cross_encoder(
    tmp_path: Path, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real cross-encoder over the real corpus: rerank runs end to end and
    honours ``top_n`` (opt-in; gated on the CE model being cached)."""
    from indexed.connectors.files.connector import FileSystemConnector

    cols = tmp_path / "cols"
    ingestion.create(
        [
            SourceConfig(
                name="files-v2", type="localFiles", base_url_or_path=str(files_corpus)
            )
        ],
        use_cache=False,
        connector_factory=lambda cfg: FileSystemConnector(path=str(files_corpus)),
        collections_path=str(cols),
    )

    monkeypatch.setattr(
        "indexed.core.v2.retrieval.resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, top_n=2),
    )
    res = retrieval.search(
        "penguin migration antarctic coastline",
        configs=[_cfg("files-v2")],
        collections_path=str(cols),
        include_matched_chunks=True,
    )
    docs = res["files-v2"]["results"]
    assert docs, "reranked search returns hits"
    assert len(docs) <= 2  # top_n respected


# --- core-v2-discoverability/2: per-call `rerank` override -------------------


def test_rerank_true_overrides_disabled_config_without_mutating_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rerank=True`` forces a rerank even when ``[core.v2.rerank]`` is
    disabled, and never mutates the resolved config object (CLI --rerank on
    one call must not leak into config.toml or later calls)."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["alpha"]), make_doc("d2", ["beta"])])

    disabled_cfg = CoreV2RerankConfig(enabled=False, model="test-ce", top_n=1)
    monkeypatch.setattr(retrieval, "resolve_rerank_config", lambda: disabled_cfg)

    applied_cfgs = []
    monkeypatch.setattr(
        retrieval,
        "_apply_rerank",
        lambda nws, q, cfg: applied_cfgs.append(cfg) or nws,
    )

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "alpha",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            rerank=True,
        )

    assert len(applied_cfgs) == 1, "rerank=True must apply rerank despite enabled=False"
    assert applied_cfgs[0].enabled is True
    assert disabled_cfg.enabled is False  # the resolved config is untouched
    assert res["c1"]["scoreKind"] == "rerank"


def test_rerank_false_overrides_enabled_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rerank=False`` suppresses rerank even when ``[core.v2.rerank]`` is
    enabled."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["alpha"])])

    monkeypatch.setattr(
        retrieval,
        "resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="test-ce", top_n=1),
    )

    def _must_not_run(nws, q, cfg):  # noqa: ANN001, ANN202
        raise AssertionError("rerank=False must not apply rerank")

    monkeypatch.setattr(retrieval, "_apply_rerank", _must_not_run)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "alpha",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            rerank=False,
        )

    assert res["c1"]["scoreKind"] != "rerank"


def test_rerank_never_writes_to_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """issue #186: enabling rerank must never write to stdout — it corrupts
    --simple-output JSON parsing even with stderr separately redirected."""
    import io

    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"])])

    monkeypatch.setattr(
        retrieval,
        "resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="x", top_n=3),
    )

    class _NoisyRerank:
        def __init__(self, *, model: str, top_n: int) -> None:
            print("a third-party library writes a warning directly to stdout")
            self._top_n = top_n

        def postprocess_nodes(self, nodes, *, query_str=None, query_bundle=None):
            return nodes[: self._top_n]

    import llama_index.core.postprocessor as pp

    monkeypatch.setattr(pp, "SentenceTransformerRerank", _NoisyRerank)

    captured = io.StringIO()
    import contextlib

    with mock_embedding(embed_dim=8):
        with contextlib.redirect_stdout(captured):
            retrieval.search(
                "penguin", configs=[_cfg("c1")], collections_path=str(cols)
            )

    assert captured.getvalue() == ""


def test_rerank_none_defers_to_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rerank=None`` (the default — no override requested) leaves the
    resolved config in charge, unchanged from before this override existed."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["alpha"])])

    monkeypatch.setattr(
        retrieval,
        "resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="test-ce", top_n=1),
    )
    monkeypatch.setattr(retrieval, "_apply_rerank", lambda nws, q, cfg: nws)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "alpha", configs=[_cfg("c1")], collections_path=str(cols)
        )

    assert res["c1"]["scoreKind"] == "rerank"


# ── query-time git awareness (#60/#144/#146) ───────────────────────────────


def _build_files_at(cols: Path, name: str, docs, base_path: Path) -> None:
    """Build a v2 collection whose manifest ``basePath`` is ``base_path``."""
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [
                SourceConfig(
                    name=name, type="localFiles", base_url_or_path=str(base_path)
                )
            ],
            use_cache=False,
            connector_factory=make_connector_factory(
                docs, {"type": "localFiles", "basePath": str(base_path)}
            ),
            collections_path=str(cols),
        )


def _commit(repo: Path, *args: str) -> None:
    from tests.conftest import run_git

    run_git(repo, *args)


def test_changed_since_keeps_only_changed_documents(
    tmp_path: Path, git_repo: Path
) -> None:
    (git_repo / "changed.txt").write_text("penguin one")
    (git_repo / "stale.txt").write_text("walrus one")
    _commit(git_repo, "add", ".")
    _commit(git_repo, "commit", "-m", "files")
    (git_repo / "changed.txt").write_text("penguin two")
    _commit(git_repo, "commit", "-am", "edit penguin")

    cols = tmp_path / "cols"
    docs = [
        make_doc("changed.txt", ["penguin migration"]),
        make_doc("stale.txt", ["walrus migration"]),
    ]
    _build_files_at(cols, "c1", docs, git_repo)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            changed_since="HEAD~1",
        )

    assert [d["id"] for d in res["c1"]["results"]] == ["changed.txt"]
    # An applied filter is reported too, so callers can tell it apart from a skip.
    assert res["c1"]["gitFilter"] == {"ref": "HEAD~1", "applied": True}


def test_changed_since_filters_before_grouping_so_max_docs_still_fills(
    tmp_path: Path, git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The filter runs on NODES, before grouping: a stale doc must not occupy a
    ``max_docs`` slot and leave the result set short."""
    for name in ("a.txt", "b.txt", "stale.txt"):
        (git_repo / name).write_text("one")
    _commit(git_repo, "add", ".")
    _commit(git_repo, "commit", "-m", "files")
    for name in ("a.txt", "b.txt"):
        (git_repo / name).write_text("two")
    _commit(git_repo, "commit", "-am", "edit two")

    cols = tmp_path / "cols"
    docs = [
        make_doc("stale.txt", ["penguin stale"]),  # first indexed on purpose
        make_doc("a.txt", ["penguin a"]),
        make_doc("b.txt", ["penguin b"]),
    ]
    _build_files_at(cols, "c1", docs, git_repo)

    seen: dict[str, set[str]] = {}
    original = retrieval._group_by_document

    def spy(nodes, **kwargs):  # noqa: ANN001, ANN003, ANN202
        seen["sources"] = {n.node.metadata["source_id"] for n in nodes}
        return original(nodes, **kwargs)

    monkeypatch.setattr(retrieval, "_group_by_document", spy)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            max_docs=2,
            changed_since="HEAD~1",
        )

    assert seen["sources"] == {"a.txt", "b.txt"}
    assert len(res["c1"]["results"]) == 2


def test_git_provenance_attaches_last_commit(tmp_path: Path, git_repo: Path) -> None:
    (git_repo / "tracked.txt").write_text("penguin")
    _commit(git_repo, "add", ".")
    _commit(git_repo, "commit", "-m", "add penguin")

    cols = tmp_path / "cols"
    _build_files_at(cols, "c1", [make_doc("tracked.txt", ["penguin"])], git_repo)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            git_provenance=True,
        )

    git = res["c1"]["results"][0]["git"]
    assert git["author"] == "Test"
    assert git["subject"] == "add penguin"
    assert git["commit"].startswith(git["short"])
    assert git["committedAt"].startswith("20")


def test_git_options_attach_nothing_when_not_requested(
    tmp_path: Path, git_repo: Path
) -> None:
    (git_repo / "tracked.txt").write_text("penguin")
    _commit(git_repo, "add", ".")
    _commit(git_repo, "commit", "-m", "add penguin")

    cols = tmp_path / "cols"
    _build_files_at(cols, "c1", [make_doc("tracked.txt", ["penguin"])], git_repo)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )

    assert "git" not in res["c1"]["results"][0]
    assert "gitFilter" not in res["c1"]


def test_git_options_are_noops_for_a_non_files_reader(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    docs = [make_doc("JIRA-1", ["penguin"])]
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [
                SourceConfig(
                    name="c1", type="jiraCloud", base_url_or_path="https://acme.test"
                )
            ],
            use_cache=False,
            connector_factory=make_connector_factory(
                docs, {"type": "jiraCloud", "baseUrl": "https://acme.test"}
            ),
            collections_path=str(cols),
        )
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            changed_since="HEAD",
            git_provenance=True,
        )

    assert [d["id"] for d in res["c1"]["results"]] == ["JIRA-1"]
    assert "git" not in res["c1"]["results"][0]
    # The filter cannot apply to a non-files reader, and says so instead of
    # quietly returning unfiltered rows.
    assert res["c1"]["gitFilter"] == {
        "ref": "HEAD",
        "applied": False,
        "reason": "not-a-files-collection",
    }


def test_changed_since_invalid_ref_skips_the_filter(
    tmp_path: Path, git_repo: Path
) -> None:
    (git_repo / "a.txt").write_text("penguin")
    _commit(git_repo, "add", ".")
    _commit(git_repo, "commit", "-m", "add a")

    cols = tmp_path / "cols"
    _build_files_at(cols, "c1", [make_doc("a.txt", ["penguin"])], git_repo)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            changed_since="no-such-ref",
        )

    assert [d["id"] for d in res["c1"]["results"]] == ["a.txt"]
    assert res["c1"]["gitFilter"] == {
        "ref": "no-such-ref",
        "applied": False,
        "reason": "unknown-ref",
    }


def test_git_options_are_noops_outside_a_repo(tmp_path: Path) -> None:
    """A files collection over a non-repo must not empty results or raise."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("penguin")

    cols = tmp_path / "cols"
    _build_files_at(cols, "c1", [make_doc("a.txt", ["penguin"])], corpus)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            changed_since="HEAD",
            git_provenance=True,
        )

    assert [d["id"] for d in res["c1"]["results"]] == ["a.txt"]
    assert "git" not in res["c1"]["results"][0]
    assert res["c1"]["gitFilter"] == {
        "ref": "HEAD",
        "applied": False,
        "reason": "no-git-repository",
    }


# ── line-level blame (#60) ─────────────────────────────────────────────────


def _spanned_doc(doc_id: str, chunks: list[tuple[str, int, int]]) -> dict:
    """A ConvertedDocument whose chunks carry the code chunker's line spans."""
    return {
        "id": doc_id,
        "url": f"u/{doc_id}",
        "modifiedTime": "2026-01-10T00:00:00+00:00",
        "text": " ".join(text for text, _s, _e in chunks),
        "chunks": [
            {"indexedData": text, "metadata": {"start_line": start, "end_line": end}}
            for text, start, end in chunks
        ],
    }


def _two_region_repo(repo: Path) -> tuple[str, str]:
    """code.py: c1 writes both regions, c2 rewrites the second one only."""
    (repo / "code.py").write_text("alpha penguin one\nbeta penguin two\n")
    _commit(repo, "add", ".")
    _commit(repo, "commit", "-m", "c1", "--date=2026-01-01T00:00:00+00:00")
    from tests.conftest import run_git

    first = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "code.py").write_text("alpha penguin one\nbeta penguin rewritten\n")
    _commit(
        repo,
        "commit",
        "-am",
        "c2",
        "--author=Second Author <second@test.com>",
        "--date=2026-01-02T00:00:00+00:00",
    )
    return first, run_git(repo, "rev-parse", "HEAD").stdout.strip()


def test_git_line_blame_attributes_each_chunk_to_its_own_commit(
    tmp_path: Path, git_repo: Path
) -> None:
    first, second = _two_region_repo(git_repo)

    cols = tmp_path / "cols"
    docs = [
        _spanned_doc(
            "code.py", [("alpha penguin one", 0, 0), ("beta penguin two", 1, 1)]
        )
    ]
    _build_files_at(cols, "c1", docs, git_repo)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            git_line_blame=True,
        )

    entry = res["c1"]["results"][0]
    # Line-level only: the document-level contract stays absent unless asked.
    assert "git" not in entry
    by_chunk = {chunk["chunkNumber"]: chunk for chunk in entry["matchedChunks"]}
    assert by_chunk[0]["git"]["commit"] == first
    assert (by_chunk[0]["git"]["startLine"], by_chunk[0]["git"]["endLine"]) == (1, 1)
    assert by_chunk[1]["git"]["commit"] == second
    assert by_chunk[1]["git"]["author"] == "Second Author"
    assert (by_chunk[1]["git"]["startLine"], by_chunk[1]["git"]["endLine"]) == (2, 2)


def test_git_line_blame_marks_uncommitted_lines(tmp_path: Path, git_repo: Path) -> None:
    _two_region_repo(git_repo)
    # An uncommitted edit to the second line, still on disk at query time.
    (git_repo / "code.py").write_text("alpha penguin one\nbeta penguin local only\n")

    cols = tmp_path / "cols"
    docs = [
        _spanned_doc(
            "code.py", [("alpha penguin one", 0, 0), ("beta penguin two", 1, 1)]
        )
    ]
    _build_files_at(cols, "c1", docs, git_repo)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            git_line_blame=True,
        )

    by_chunk = {
        chunk["chunkNumber"]: chunk
        for chunk in res["c1"]["results"][0]["matchedChunks"]
    }
    assert "git" in by_chunk[0]
    # The edited chunk's last touch is the working tree — named, not dressed up
    # as the committed ancestor it replaced.
    assert by_chunk[1]["git"]["uncommitted"] is True


def test_git_line_blame_omits_the_field_for_chunks_without_a_line_span(
    tmp_path: Path, git_repo: Path
) -> None:
    (git_repo / "plain.txt").write_text("penguin")
    _commit(git_repo, "add", ".")
    _commit(git_repo, "commit", "-m", "add penguin")

    cols = tmp_path / "cols"
    _build_files_at(cols, "c1", [make_doc("plain.txt", ["penguin"])], git_repo)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            git_line_blame=True,
        )

    chunk = res["c1"]["results"][0]["matchedChunks"][0]
    # No span, no answer: a chunk without one never borrows the file-level commit.
    assert "git" not in chunk


def test_git_line_blame_costs_one_blame_call_per_admitted_document(
    tmp_path: Path, git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bound is admitted documents (≤ max_docs), never nodes × chunks."""
    _two_region_repo(git_repo)  # code.py, two lines, two commits
    for name in ("alpha.py", "beta.py"):
        (git_repo / name).write_text(f"{name} walrus one\n{name} walrus two\n")
    _commit(git_repo, "add", ".")
    _commit(git_repo, "commit", "-m", "two more files")

    cols = tmp_path / "cols"
    docs = [
        _spanned_doc(
            "alpha.py", [("alpha walrus one", 0, 0), ("alpha walrus two", 1, 1)]
        ),
        _spanned_doc("beta.py", [("beta walrus one", 0, 0), ("beta walrus two", 1, 1)]),
    ]
    _build_files_at(cols, "c1", docs, git_repo)

    calls: list[str] = []
    original = retrieval.git_meta.blame_lines

    def counting(repo: str, path: str):
        calls.append(path)
        return original(repo, path)

    monkeypatch.setattr(retrieval.git_meta, "blame_lines", counting)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "walrus",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            max_docs=1,
            git_line_blame=True,
        )

    assert len(res["c1"]["results"]) == 1
    # One document admitted (two matched chunks of it) → exactly one blame.
    assert len(calls) == 1
    assert calls[0] in {"alpha.py", "beta.py"}


def test_git_line_blame_omits_the_field_outside_a_repo(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "code.py").write_text("penguin\n")

    cols = tmp_path / "cols"
    docs = [_spanned_doc("code.py", [("alpha penguin one", 0, 0)])]
    _build_files_at(cols, "c1", docs, corpus)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            git_line_blame=True,
        )

    assert [d["id"] for d in res["c1"]["results"]] == ["code.py"]
    assert "git" not in res["c1"]["results"][0]["matchedChunks"][0]
