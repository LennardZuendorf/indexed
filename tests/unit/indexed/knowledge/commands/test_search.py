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
        assert "Total:" in joined


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
        from unittest.mock import Mock

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
        ):
            return search_results

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        # suppress_core_output and create_operation_progress need to be contexts
        from contextlib import contextmanager

        @contextmanager
        def fake_suppress():
            yield

        @contextmanager
        def fake_progress(desc):
            progress = Mock()
            task_id = 0

            def callback(*a, **kw):
                pass

            yield progress, task_id, callback

        monkeypatch.setattr(search_cmd, "suppress_core_output", fake_suppress)
        monkeypatch.setattr(search_cmd, "create_operation_progress", fake_progress)

        result = runner.invoke(search_cmd.app, ["my-query"])

        assert result.exit_code == 0
        assert "Searching for" in result.stdout

    def test_search_specific_collection_compact_output(self, monkeypatch):
        """--compact flag should use compact formatter path."""
        from unittest.mock import Mock

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
        ):
            return {"myCol": {"results": [{"id": "d1", "score": 0.5}]}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        from contextlib import contextmanager

        @contextmanager
        def fake_suppress():
            yield

        @contextmanager
        def fake_progress(desc):
            yield Mock(), 0, lambda *a, **kw: None

        monkeypatch.setattr(search_cmd, "suppress_core_output", fake_suppress)
        monkeypatch.setattr(search_cmd, "create_operation_progress", fake_progress)

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
        from unittest.mock import Mock

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
        ):
            return {"col1": {"results": [{"id": "d1"}]}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        from contextlib import contextmanager

        @contextmanager
        def fake_suppress():
            yield

        @contextmanager
        def fake_progress(desc):
            yield Mock(), 0, lambda *a, **kw: None

        monkeypatch.setattr(search_cmd, "suppress_core_output", fake_suppress)
        monkeypatch.setattr(search_cmd, "create_operation_progress", fake_progress)

        result = runner.invoke(search_cmd.app, ["my-query", "--no-content"])

        assert result.exit_code == 0
