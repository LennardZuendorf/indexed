"""Engine result -> eval hits: the one place that knows the result dialect."""

from __future__ import annotations

from typing import Any, Dict

from indexed.eval.adapter import (
    document_identity,
    document_ranking,
    hits_from_engine_result,
    ranking_detail,
)


def _payload(
    results, *, score_kind="cosine", model="sentence-transformers/all-MiniLM-L6-v2"
):
    return {
        "c1": {
            "collectionName": "c1",
            "indexerName": model,
            "scoreKind": score_kind,
            "results": results,
        }
    }


def _doc(doc_id, path, chunks):
    return {"id": doc_id, "url": path, "path": path, "matchedChunks": chunks}


def test_documents_keep_engine_order_and_flatten_their_chunks() -> None:
    result = _payload(
        [
            _doc("b.md", "file:///corpus/b.md", [{"chunkNumber": 2, "score": 0.9}]),
            _doc("a.md", "file:///corpus/a.md", [{"chunkNumber": 0, "score": 0.8}]),
        ]
    )
    hits, error = hits_from_engine_result(result, collection="c1")
    assert error is None
    assert [hit.doc_name for hit in hits] == ["b.md", "a.md"]
    assert [hit.rank for hit in hits] == [1, 2]
    assert hits[0].chunk == 2
    assert hits[0].score == 0.9
    assert hits[0].score_kind == "cosine"
    assert document_ranking(hits) == ["b.md", "a.md"]


def test_file_uris_and_bare_names_normalise_to_the_same_identity() -> None:
    assert document_identity({"id": "plan.md", "path": "file:///corpus/plan.md"}) == (
        "plan.md",
        "plan.md",
    )
    assert (
        document_identity({"id": "", "path": "file:///corpus/Plan.MD"})[1] == "plan.md"
    )
    assert document_identity({"id": "issue-1"})[1] == "issue-1"


def test_a_collection_error_is_reported_separately() -> None:
    result: Dict[str, Any] = {"c1": {"error": "collection missing"}}
    hits, error = hits_from_engine_result(result, collection="c1")
    assert hits == []
    assert error == "c1: collection missing"


def test_a_document_without_matched_chunks_still_counts_as_a_hit() -> None:
    result = _payload([{"id": "a.md", "path": "file:///corpus/a.md"}])
    hits, error = hits_from_engine_result(result, collection="c1")
    assert error is None
    assert len(hits) == 1
    assert hits[0].chunk == -1
    assert hits[0].score == 0.0


def test_ranking_detail_dedupes_documents_and_honours_top_k() -> None:
    result = _payload(
        [
            _doc(
                "a.md",
                "file:///corpus/a.md",
                [{"chunkNumber": 0, "score": 0.9}, {"chunkNumber": 1, "score": 0.7}],
            ),
            _doc("b.md", "file:///corpus/b.md", [{"chunkNumber": 0, "score": 0.5}]),
        ]
    )
    hits, _ = hits_from_engine_result(result, collection="c1")
    detail = ranking_detail(hits)
    assert [entry["doc"] for entry in detail] == ["a.md", "b.md"]
    assert detail[0]["chunk"] == 0
    assert len(ranking_detail(hits, top_k=1)) == 1


def test_unexpected_payload_shapes_never_raise() -> None:
    hits, error = hits_from_engine_result({"c1": "not-a-dict"}, collection="c1")
    assert hits == []
    assert error is not None
    hits, error = hits_from_engine_result("not-a-dict", collection="c1")  # type: ignore[arg-type]
    assert hits == []
    assert "unexpected result type" in str(error)


def test_a_payload_without_a_result_list_is_an_error_not_zero_hits() -> None:
    """An envelope this adapter does not understand must not score as a miss."""
    for results in (None, {"0": {"id": "a.md"}}, "a.md"):
        hits, error = hits_from_engine_result(
            {"c1": {"results": results}}, collection="c1"
        )
        assert hits == []
        assert "no 'results' list" in str(error)


def test_a_null_chunk_number_reads_as_the_document_sentinel() -> None:
    result = _payload(
        [_doc("a.md", "file:///corpus/a.md", [{"chunkNumber": None, "score": 0.4}])]
    )
    hits, error = hits_from_engine_result(result, collection="c1")
    assert error is None
    assert hits[0].chunk == -1
    assert hits[0].score == 0.4
