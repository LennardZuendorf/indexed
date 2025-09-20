from main.services.search_service import SearchService


def test_search_service_applies_args(monkeypatch):
    calls = {}

    class FakeSearcher:
        def search(self, query, *, max_number_of_chunks, max_number_of_documents, include_text_content, include_all_chunks_content, include_matched_chunks_content):  # noqa: E501
            calls["query"] = query
            calls["max_number_of_chunks"] = max_number_of_chunks
            calls["max_number_of_documents"] = max_number_of_documents
            calls["include_text_content"] = include_text_content
            calls["include_all_chunks_content"] = include_all_chunks_content
            calls["include_matched_chunks_content"] = include_matched_chunks_content
            return {"results": []}

    svc = SearchService()

    # Patch _get_searcher to avoid file IO
    monkeypatch.setattr(svc, "_get_searcher", lambda name, index: FakeSearcher())

    # Patch _discover_collections to single collection
    monkeypatch.setattr(svc, "_discover_collections", lambda: ["c1"])
    monkeypatch.setattr(svc, "_get_default_indexer", lambda name: "idx")

    result = svc.search(
        "q",
        configs=None,
        max_chunks=12,
        max_docs=4,
        include_full_text=True,
        include_all_chunks=False,
        include_matched_chunks=True,
    )

    assert "c1" in result
    assert calls["query"] == "q"
    assert calls["max_number_of_chunks"] == 12
    assert calls["max_number_of_documents"] == 4
    assert calls["include_text_content"] is True
    assert calls["include_all_chunks_content"] is False
    assert calls["include_matched_chunks_content"] is True



