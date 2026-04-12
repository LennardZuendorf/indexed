"""Tests for MCP tool helper functions.

Focuses on the pure helper functions in indexed.mcp.tools that convert
between v2 search output and the v1-compatible display format consumed by
the LLM formatter.
"""


class TestNormalizeV2Results:
    """Pure-function tests for _normalize_v2_results in tools.py."""

    def test_single_collection_format(self) -> None:
        """Single-collection v2 result maps collectionName to top-level key."""
        from indexed.mcp.tools import _normalize_v2_results

        raw = {"collectionName": "docs", "results": [{"text": "hello"}]}
        out = _normalize_v2_results(raw)
        assert out == {"docs": {"results": [{"text": "hello"}]}}

    def test_multi_collection_format(self) -> None:
        """Multi-collection v2 result flattens collections list into dict."""
        from indexed.mcp.tools import _normalize_v2_results

        raw = {
            "collections": [
                {"collectionName": "a", "results": [{"text": "x"}]},
                {"collectionName": "b", "results": []},
            ]
        }
        out = _normalize_v2_results(raw)
        assert out == {
            "a": {"results": [{"text": "x"}]},
            "b": {"results": []},
        }

    def test_empty_collections_list(self) -> None:
        """Multi-collection result with empty list normalizes to empty dict."""
        from indexed.mcp.tools import _normalize_v2_results

        raw = {"collections": []}
        out = _normalize_v2_results(raw)
        assert out == {}

    def test_missing_results_key_defaults_to_empty(self) -> None:
        """Single-collection missing results key falls back to empty list."""
        from indexed.mcp.tools import _normalize_v2_results

        raw = {"collectionName": "docs"}
        out = _normalize_v2_results(raw)
        assert out == {"docs": {"results": []}}

    def test_preserves_result_structure(self) -> None:
        """Each result dict is kept as-is without transformation."""
        from indexed.mcp.tools import _normalize_v2_results

        chunk = {"id": "c1", "score": 0.9, "content": {"indexedData": "text"}}
        raw = {"collectionName": "docs", "results": [chunk]}
        out = _normalize_v2_results(raw)
        assert out["docs"]["results"][0] is chunk
