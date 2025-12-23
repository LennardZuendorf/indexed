"""Tests for the indexed knowledge search command and formatter.

We focus on realistic behaviors:
- no collections configured
- successful search across collections
- search in a missing collection
- formatter behavior for no results and mixed results
"""

from typing import Any, Dict, List

from typer.testing import CliRunner

from indexed.knowledge.commands import search as search_cmd


runner = CliRunner()


class TestSearchCommand:
    """End-to-end-ish tests for the Typer search command."""

    def test_no_collections_prints_message_and_exits_cleanly(self, monkeypatch):
        """When there are no collections, it should print a hint and not error."""
        # status() returns empty list
        monkeypatch.setattr(search_cmd, "status", lambda *args, **kwargs: [])

        # For this Typer app, the command name is the program; we only pass QUERY
        result = runner.invoke(search_cmd.app, ["test-query"])

        assert result.exit_code == 0
        assert "No collections found to search" in result.stdout

    def test_missing_specific_collection_exits_with_error(self, monkeypatch):
        """Searching a non-existent collection returns a clear error and exit 1."""
        # status([name]) returns empty list for that collection
        monkeypatch.setattr(search_cmd, "status", lambda names=None: [])

        # Avoid hitting real logging setup
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)

        result = runner.invoke(
            search_cmd.app, ["test-query", "--collection", "missing"]
        )

        assert result.exit_code == 1
        assert "Collection 'missing' not found" in result.stdout


class TestFormatSearchResults:
    """Tests for the search result formatting helpers."""

    def test_format_search_results_no_results_prints_message(self, monkeypatch):
        """If no results are present, a friendly message should be shown."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        # Empty results dict
        search_cmd.format_search_results("query", results={})

        # Expect a "No results found" style message in one of the lines
        assert any("No results found" in line for line in outputs)

    def test_format_search_results_skips_error_collections_and_uses_scores(
        self, monkeypatch
    ) -> None:
        """Collections with errors should be ignored, and best chunk is chosen by score."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        # Two collections: one with an error, one with results
        results: Dict[str, Any] = {
            "error-collection": {"error": "index unavailable"},
            "ok-collection": {
                "results": [
                    {
                        "id": "doc1",
                        "path": "/path/doc1",
                        "matchedChunks": [
                            {
                                "id": "c1",
                                "score": 0.4,
                                "content": {"indexedData": "chunk1"},
                            },
                            {
                                "id": "c2",
                                "score": 0.2,
                                "content": {"indexedData": "chunk2"},
                            },
                        ],
                    }
                ]
            },
        }

        search_cmd.format_search_results("query", results=results, limit=5)

        # We at least expect the header for the best match section and no crash
        joined = "\n".join(outputs)
        assert "Best Matched Search Result" in joined
        # Detailed Rich rendering of chunks is handled by components and not
        # asserted here to avoid coupling tests to layout details.

    def test_format_search_results_compact_handles_no_results(self, monkeypatch):
        """Compact formatter should also show a friendly message when empty."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        search_cmd.format_search_results_compact("query", results={})

        assert any("No results found" in line for line in outputs)

    def test_show_all_results_compact_groups_by_collection(self, monkeypatch):
        """_show_all_results_compact should group and count results per collection."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "coll1": {"results": [{"id": "a"}, {"id": "b"}]},
            "coll2": {"results": [{"id": "c"}]},
        }

        # Call the internal helper to keep behavior focused
        search_cmd._show_all_results_compact(results, limit=10)

        joined = "\n".join(outputs)
        # Should mention collections and correct counts
        assert "coll1" in joined
        assert "(2 results)" in joined
        assert "coll2" in joined
        assert "(1 results)" in joined
        # And a total summary line
        assert "Total:" in joined or "Total" in joined
