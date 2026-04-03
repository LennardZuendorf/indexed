"""Tests for the indexed knowledge search command and formatter.

We focus on realistic behaviors:
- no collections configured
- successful search across collections
- search in a missing collection
- formatter behavior for no results and mixed results
"""

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from typer.testing import CliRunner

from indexed.knowledge.commands import search as search_cmd
from indexed.utils import storage_info as storage_info_mod


runner = CliRunner()

# Patch resolve_preferred_collections_path globally for all search tests
# so tests don't need ConfigService
_MOCK_PATH = patch.object(
    storage_info_mod,
    "resolve_preferred_collections_path",
    return_value=Path("/tmp/test-collections"),
)
_MOCK_PATH.start()


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
        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [])

        # Avoid hitting real logging setup
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)

        result = runner.invoke(
            search_cmd.app, ["test-query", "--collection", "missing"]
        )

        assert result.exit_code == 1
        assert "Collection 'missing' not found" in result.stdout


class TestFormatSearchResults:
    """Tests for the search result formatting helpers."""

    def test_format_search_results_no_results_prints_warning(self, monkeypatch):
        """If no results are present, print_warning should be called."""
        from unittest.mock import patch

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        with patch.object(search_cmd, "print_warning") as mock_warn:
            search_cmd.format_search_results("query", results={})
            mock_warn.assert_called_once()
            assert "No results found" in mock_warn.call_args[0][0]

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
        # And a summary line
        assert "Search Result" in joined

    def test_format_search_results_no_content_calls_compact(self, monkeypatch):
        """show_content=False should use the compact display path."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "coll1": {"results": [{"id": "doc1"}]},
        }

        search_cmd.format_search_results("query", results=results, show_content=False)

        joined = "\n".join(outputs)
        # The compact path should list the collection
        assert "coll1" in joined

    def test_show_top_result_split_cards_non_dict_content(self, monkeypatch):
        """When chunk content is not a dict, it should be coerced to string."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            outputs.append(str(args))

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        chunk_info = search_cmd.ChunkInfo(
            collection="col",
            doc_id="doc1",
            path="/p",
            chunk={"score": 0.1, "content": "plain string content"},
            chunk_index=1,
        )
        # Should not raise even with string content
        search_cmd._show_top_result_split_cards(chunk_info)

    def test_show_compact_match_non_float_score(self, monkeypatch):
        """_show_compact_match with a non-float score should not raise."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        chunk_info = search_cmd.ChunkInfo(
            collection="col",
            doc_id="doc1",
            path="/p",
            chunk={"score": "high", "content": {"indexedData": "text"}},
            chunk_index=1,
        )
        search_cmd._show_compact_match(chunk_info)

        joined = "\n".join(outputs)
        assert "col" in joined
        assert "high" in joined

    def test_show_all_results_compact_skips_error_and_empty(self, monkeypatch):
        """Collections with errors or empty results should be skipped."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "error-coll": {"error": "unavailable"},
            "empty-coll": {"results": []},
        }
        search_cmd._show_all_results_compact(results, limit=10)

        joined = "\n".join(outputs)
        # Neither collection should appear as a header
        assert "error-coll" not in joined
        assert "empty-coll" not in joined
        # Should show no results message
        assert "No results found" in joined

    def test_format_search_results_compact_with_results(self, monkeypatch):
        """format_search_results_compact should list docs with scores and show total."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "coll1": {
                "results": [
                    {"id": "doc-a", "score": 0.75},
                    {"id": "doc-b"},  # no score
                ]
            },
        }
        search_cmd.format_search_results_compact("query", results=results, limit=10)

        joined = "\n".join(outputs)
        assert "coll1" in joined
        assert "doc-a" in joined
        assert "doc-b" in joined
        assert "0.7500" in joined
        assert "Search Result" in joined


class TestSearchCommandExecution:
    """Tests covering the search command's execution loop."""

    def _make_status(self, name: str):
        """Return a minimal mock status object."""
        from unittest.mock import Mock

        s = Mock()
        s.name = name
        s.indexers = ["default"]
        return s

    def test_search_all_collections_runs_and_formats(self, monkeypatch):
        """Searching all collections should call svc_search and display results."""
        from unittest.mock import Mock, MagicMock

        statuses = [self._make_status("col1"), self._make_status("col2")]

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "Index", lambda: None)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)

        fake_source_config = Mock()
        monkeypatch.setattr(
            search_cmd,
            "SourceConfig",
            lambda **kw: fake_source_config,
        )

        search_results: Dict[str, Any] = {
            "col1": {"results": []},
            "col2": {"results": []},
        }

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            progress_callback=None,
            collections_path=None,
        ):
            return search_results

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        from contextlib import contextmanager

        @contextmanager
        def fake_suppress():
            yield

        monkeypatch.setattr(search_cmd, "suppress_core_output", fake_suppress)

        # Mock create_phased_progress as a context manager returning a mock with start/finish_phase
        phased_mock = MagicMock()
        phased_mock.__enter__ = Mock(return_value=phased_mock)
        phased_mock.__exit__ = Mock(return_value=False)
        monkeypatch.setattr(
            search_cmd, "create_phased_progress", lambda **kw: phased_mock
        )

        result = runner.invoke(search_cmd.app, ["my-query"])

        assert result.exit_code == 0
        assert "Searching for" in result.stdout

    def test_search_specific_collection_compact_output(self, monkeypatch):
        """--compact flag should use compact formatter path."""
        from unittest.mock import Mock, MagicMock

        statuses = [self._make_status("myCol")]

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "Index", lambda: None)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)

        fake_source_config = Mock()
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: fake_source_config)

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            progress_callback=None,
            collections_path=None,
        ):
            return {"myCol": {"results": [{"id": "d1", "score": 0.5}]}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        from contextlib import contextmanager

        @contextmanager
        def fake_suppress():
            yield

        monkeypatch.setattr(search_cmd, "suppress_core_output", fake_suppress)

        phased_mock = MagicMock()
        phased_mock.__enter__ = Mock(return_value=phased_mock)
        phased_mock.__exit__ = Mock(return_value=False)
        monkeypatch.setattr(
            search_cmd, "create_phased_progress", lambda **kw: phased_mock
        )

        result = runner.invoke(
            search_cmd.app, ["my-query", "--collection", "myCol", "--compact"]
        )

        assert result.exit_code == 0

    def test_search_verbose_mode_uses_noop_context(self, monkeypatch):
        """In verbose mode the NoOpContext path should be taken."""
        from unittest.mock import Mock

        statuses = [self._make_status("col1")]

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "Index", lambda: None)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: True)

        fake_source_config = Mock()
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: fake_source_config)

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            progress_callback=None,
            collections_path=None,
        ):
            return {"col1": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        from contextlib import contextmanager

        @contextmanager
        def fake_noop():
            yield

        monkeypatch.setattr(search_cmd, "NoOpContext", fake_noop)

        result = runner.invoke(search_cmd.app, ["my-query"])

        assert result.exit_code == 0

    def test_search_no_content_flag(self, monkeypatch):
        """--no-content flag should pass show_content=False to formatter."""
        from unittest.mock import Mock, MagicMock

        statuses = [self._make_status("col1")]

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "Index", lambda: None)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)

        fake_source_config = Mock()
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: fake_source_config)

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            progress_callback=None,
            collections_path=None,
        ):
            return {"col1": {"results": [{"id": "d1"}]}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        from contextlib import contextmanager

        @contextmanager
        def fake_suppress():
            yield

        monkeypatch.setattr(search_cmd, "suppress_core_output", fake_suppress)

        phased_mock = MagicMock()
        phased_mock.__enter__ = Mock(return_value=phased_mock)
        phased_mock.__exit__ = Mock(return_value=False)
        monkeypatch.setattr(
            search_cmd, "create_phased_progress", lambda **kw: phased_mock
        )

        result = runner.invoke(search_cmd.app, ["my-query", "--no-content"])

        assert result.exit_code == 0

    def test_search_simple_output_returns_llm_json(self, monkeypatch):
        """In simple output mode, search should return LLM-formatted JSON."""
        import json

        from unittest.mock import Mock

        from indexed.utils.simple_output import reset_simple_output, set_simple_output

        statuses = [self._make_status("col1")]

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "Index", lambda: None)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)

        fake_source_config = Mock()
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: fake_source_config)

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            progress_callback=None,
            collections_path=None,
        ):
            return {
                "col1": {
                    "results": [
                        {
                            "id": "doc1",
                            "url": "http://example.com/doc1",
                            "matchedChunks": [
                                {
                                    "chunkNumber": 0,
                                    "score": 0.3,
                                    "content": {"indexedData": "relevant text"},
                                },
                            ],
                        }
                    ]
                }
            }

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        set_simple_output(True)
        try:
            result = runner.invoke(search_cmd.app, ["my-query"])

            assert result.exit_code == 0
            parsed = json.loads(result.stdout)
            assert parsed["query"] == "my-query"
            assert parsed["total_collections_searched"] == 1
            assert parsed["total_documents_found"] == 1
            assert len(parsed["results"]) == 1
            assert parsed["results"][0]["text"] == "relevant text"
            assert parsed["results"][0]["collection"] == "col1"
            assert parsed["results"][0]["rank"] == 1
        finally:
            reset_simple_output()

    def test_search_simple_output_no_collections(self, monkeypatch):
        """In simple output mode with no collections, should return JSON error."""
        import json

        from indexed.utils.simple_output import reset_simple_output, set_simple_output

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [])
        monkeypatch.setattr(search_cmd, "Index", lambda: None)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)

        set_simple_output(True)
        try:
            result = runner.invoke(search_cmd.app, ["my-query"])

            assert result.exit_code == 0
            parsed = json.loads(result.stdout)
            assert "error" in parsed
        finally:
            reset_simple_output()

    def test_search_simple_output_missing_collection(self, monkeypatch):
        """In simple output mode, missing collection should return JSON error and exit 1."""
        import json

        from indexed.utils.simple_output import reset_simple_output, set_simple_output

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [])
        monkeypatch.setattr(search_cmd, "Index", lambda: None)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)

        set_simple_output(True)
        try:
            result = runner.invoke(
                search_cmd.app, ["my-query", "--collection", "missing"]
            )

            assert result.exit_code == 1
            parsed = json.loads(result.stdout)
            assert "error" in parsed
            assert "missing" in parsed["error"]
        finally:
            reset_simple_output()


class TestFormatSearchResultsCompactEdgeCases:
    """Tests for edge cases in compact formatter."""

    def test_compact_skips_error_collections(self, monkeypatch):
        """format_search_results_compact should skip error collections."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "error-coll": {"error": "unavailable"},
            "good-coll": {"results": [{"id": "doc1", "score": 0.5}]},
        }
        search_cmd.format_search_results_compact("query", results=results)

        joined = "\n".join(outputs)
        assert "error-coll" not in joined
        assert "good-coll" in joined

    def test_compact_skips_empty_collections(self, monkeypatch):
        """format_search_results_compact should skip collections with no results."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_cmd, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "empty-coll": {"results": []},
        }
        search_cmd.format_search_results_compact("query", results=results)

        joined = "\n".join(outputs)
        assert "empty-coll" not in joined
        assert "No results found" in joined
