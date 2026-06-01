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


class TestResolveEngineForCollection:
    """Per-collection engine resolution helper used by tools and resources."""

    def _write_manifest(self, root, name: str, payload: dict) -> None:
        import json
        from pathlib import Path

        coll = Path(root) / name
        coll.mkdir(parents=True, exist_ok=True)
        (coll / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_v2_manifest_returns_v2(self, monkeypatch, tmp_path) -> None:
        from indexed.mcp.config import resolve_engine_for_collection
        from indexed.utils import storage_info as storage_info_mod

        self._write_manifest(tmp_path, "docs", {"name": "docs", "version": "2.0"})
        monkeypatch.setattr(
            storage_info_mod,
            "resolve_preferred_collections_path",
            lambda: tmp_path,
        )

        assert resolve_engine_for_collection("docs", None, lambda: "v1") == "v2"

    def test_v1_manifest_returns_v1(self, monkeypatch, tmp_path) -> None:
        from indexed.mcp.config import resolve_engine_for_collection
        from indexed.utils import storage_info as storage_info_mod

        self._write_manifest(
            tmp_path, "docs", {"collectionName": "docs", "indexers": []}
        )
        monkeypatch.setattr(
            storage_info_mod,
            "resolve_preferred_collections_path",
            lambda: tmp_path,
        )

        # Loader returns v2 — but manifest says v1, manifest wins.
        assert resolve_engine_for_collection("docs", None, lambda: "v2") == "v1"

    def test_missing_manifest_falls_back_to_loader(self, monkeypatch, tmp_path) -> None:
        from indexed.mcp.config import resolve_engine_for_collection
        from indexed.utils import storage_info as storage_info_mod

        monkeypatch.setattr(
            storage_info_mod,
            "resolve_preferred_collections_path",
            lambda: tmp_path,
        )

        assert resolve_engine_for_collection("ghost", None, lambda: "v2") == "v2"

    def test_empty_collection_name_uses_loader(self, monkeypatch, tmp_path) -> None:
        from indexed.mcp.config import resolve_engine_for_collection
        from indexed.utils import storage_info as storage_info_mod

        monkeypatch.setattr(
            storage_info_mod,
            "resolve_preferred_collections_path",
            lambda: tmp_path,
        )

        assert resolve_engine_for_collection("", None, lambda: "v2") == "v2"
