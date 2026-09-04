"""Tests for the indexed knowledge search command and formatter.

We focus on realistic behaviors:
- no collections configured
- successful search across collections
- search in a missing collection
- formatter behavior for no results and mixed results
"""

import re
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from indexed.cli.knowledge.commands import search as search_cmd
from indexed.cli.knowledge.commands import search_render

pytestmark = pytest.mark.unit

runner = CliRunner()


def _mock_runtime_context():
    mock_config = MagicMock()
    mock_config.resolve_storage_mode.return_value = "global"
    mock_config.get_workspace_preference.return_value = None
    mock_config.store.read.return_value = {}
    return type(
        "MockCtx",
        (),
        {
            "collections_path": Path("/tmp/test-collections"),
            "mode": "global",
            "config_service": mock_config,
        },
    )()


@pytest.fixture(autouse=True)
def _patch_runtime_context():
    with (
        patch(
            "indexed.cli.composition.resolve_collections_context",
            side_effect=lambda *args, **kwargs: _mock_runtime_context(),
        ),
        patch(
            "indexed.cli.utils.storage_info.display_storage_mode_for_command",
            lambda *args, **kwargs: None,
        ),
    ):
        yield


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


class TestIsContentFree:
    """Unit tests for the content-free filename-chunk helper (M1)."""

    def test_content_matches_full_doc_id_is_content_free(self):
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/auth.py",
            path="/p",
            chunk={"score": 0.1, "content": {"indexedData": "src/auth.py"}},
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is True

    def test_content_matches_basename_only_is_content_free(self):
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/nested/auth.py",
            path="/p",
            chunk={"score": 0.1, "content": {"indexedData": "auth.py"}},
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is True

    def test_real_content_is_not_content_free(self):
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/auth.py",
            path="/p",
            chunk={
                "score": 0.1,
                "content": {"indexedData": "def authenticate(): ..."},
            },
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is False

    def test_missing_content_key_is_not_content_free(self):
        """No 'content' key at all (matched-chunk content not requested) —
        behavior must be unchanged, so this does NOT count as content-free."""
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/auth.py",
            path="/p",
            chunk={"score": 0.1},
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is False

    def test_empty_indexed_data_string_is_content_free(self):
        """A present-but-empty indexedData string has nothing useful to show
        as an excerpt, so it counts as content-free (unlike genuinely MISSING
        content, which is left unchanged — see the tests below)."""
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/auth.py",
            path="/p",
            chunk={"score": 0.1, "content": {"indexedData": ""}},
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is True

    def test_indexed_data_key_present_but_none_is_not_content_free(self):
        """indexedData explicitly None (key present, value None) is treated
        as MISSING content — behavior must be unchanged, not content-free."""
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/auth.py",
            path="/p",
            chunk={"score": 0.1, "content": {"indexedData": None}},
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is False

    def test_content_dict_missing_indexed_data_key_is_not_content_free(self):
        """A 'content' dict that doesn't carry an 'indexedData' key at all is
        MISSING content — behavior must be unchanged, not content-free."""
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/auth.py",
            path="/p",
            chunk={"score": 0.1, "content": {"metadata": {}}},
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is False

    def test_non_dict_content_is_not_content_free(self):
        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="src/auth.py",
            path="/p",
            chunk={"score": 0.1, "content": "plain string"},
            chunk_index=1,
        )
        assert search_render._is_content_free(chunk_info) is False


class TestFormatSearchResults:
    """Tests for the search result formatting helpers."""

    def test_format_search_results_no_results_prints_warning(self, monkeypatch):
        """If no results are present, print_warning should be called."""
        from unittest.mock import patch

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        with patch.object(search_render, "print_warning") as mock_warn:
            search_render.format_search_results("query", results={})
            mock_warn.assert_called_once()
            assert "No results found" in mock_warn.call_args[0][0]

    def test_format_search_results_skips_error_collections_and_uses_scores(
        self, monkeypatch
    ) -> None:
        """Collections with errors are excluded from chunk ranking (best chunk
        still chosen by score across the surviving collections), but the
        failure itself must be surfaced, not silently dropped (foundation/6
        E10, CLI twin of the MCP formatting bug)."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
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

        with patch.object(search_render, "print_error") as mock_error:
            search_render.format_search_results("query", results=results, limit=5)

        # We at least expect the header for the best match section and no crash
        joined = "\n".join(outputs)
        assert "Best Matched Search Result" in joined
        # Detailed Rich rendering of chunks is handled by components and not
        # asserted here to avoid coupling tests to layout details.

        # The failed collection must reach the user instead of vanishing.
        mock_error.assert_called_once()
        error_message = mock_error.call_args[0][0]
        assert "error-collection" in error_message
        assert "index unavailable" in error_message

    def test_format_search_results_v2_cosine_scorekind_sorts_best_first(
        self, monkeypatch
    ):
        """R13/R11 (v2 side): a collection recording ``scoreKind: cosine``
        (higher is better) must show its BEST (highest-score) chunk as the
        top result, not the lowest — the CLI twin of the MCP formatting fix.
        A v1 collection (no 'scoreKind' key) keeps the existing ascending
        sort byte-identical (R6)."""
        captured: Dict[str, Any] = {}

        def fake_show_top(chunk_info, **kwargs):
            captured["top"] = chunk_info

        monkeypatch.setattr(
            search_render, "_show_top_result_split_cards", fake_show_top
        )
        monkeypatch.setattr(search_render, "_show_compact_match", lambda *_, **__: None)

        results: Dict[str, Any] = {
            "v2-coll": {
                "scoreKind": "cosine",
                "results": [
                    {
                        "id": "worst",
                        "matchedChunks": [
                            {"score": 0.02, "content": {"indexedData": "low"}}
                        ],
                    },
                    {
                        "id": "best",
                        "matchedChunks": [
                            {"score": 0.91, "content": {"indexedData": "high"}}
                        ],
                    },
                ],
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        assert captured["top"]["doc_id"] == "best"

    def test_mixed_engines_rank_on_unified_relevance(self, monkeypatch):
        """R11 (CLI): with BOTH engines merged, chunks rank on one comparable
        measure — cosine, v1's squared-L2 mapped ``sim = 1 - d²/2`` — so a
        better v2 hit outranks a worse v1 hit AND a truly-better v1 hit still
        leads (not 'v2 always first')."""
        order: List[str] = []
        monkeypatch.setattr(
            search_render,
            "_show_top_result_split_cards",
            lambda ci, **kw: order.append(ci["doc_id"]),
        )
        monkeypatch.setattr(
            search_render,
            "_show_compact_match",
            lambda ci, **kw: order.append(ci["doc_id"]),
        )
        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        results: Dict[str, Any] = {
            "v1-coll": {
                "results": [
                    {
                        "id": "v1-strong",
                        "matchedChunks": [
                            {"score": 0.1, "content": {"indexedData": "a"}}
                        ],
                    },
                    {
                        "id": "v1-weak",
                        "matchedChunks": [
                            {"score": 1.6, "content": {"indexedData": "b"}}
                        ],
                    },
                ]
            },
            "v2-coll": {
                "scoreKind": "cosine",
                "results": [
                    {
                        "id": "v2-strong",
                        "matchedChunks": [
                            {"score": 0.9, "content": {"indexedData": "c"}}
                        ],
                    },
                    {
                        "id": "v2-weak",
                        "matchedChunks": [
                            {"score": 0.4, "content": {"indexedData": "d"}}
                        ],
                    },
                ],
            },
        }

        search_render.format_search_results("query", results=results, limit=5)

        # relevances: v1-strong .95 > v2-strong .90 > v2-weak .40 > v1-weak .20
        assert order == ["v1-strong", "v2-strong", "v2-weak", "v1-weak"]

    def test_v1_only_keeps_ascending_raw_score_order(self, monkeypatch):
        """R6 (CLI): a v1-only view (no scoreKind anywhere) keeps the EXACT
        pre-feature ascending raw-distance order — unchanged by the R11 work."""
        order: List[str] = []
        monkeypatch.setattr(
            search_render,
            "_show_top_result_split_cards",
            lambda ci, **kw: order.append(ci["doc_id"]),
        )
        monkeypatch.setattr(
            search_render,
            "_show_compact_match",
            lambda ci, **kw: order.append(ci["doc_id"]),
        )
        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        results: Dict[str, Any] = {
            "v1-coll": {
                "results": [
                    {
                        "id": "worst",
                        "matchedChunks": [
                            {"score": 3.0, "content": {"indexedData": "a"}}
                        ],
                    },
                    {
                        "id": "best",
                        "matchedChunks": [
                            {"score": 0.1, "content": {"indexedData": "b"}}
                        ],
                    },
                    {
                        "id": "mid",
                        "matchedChunks": [
                            {"score": 1.0, "content": {"indexedData": "c"}}
                        ],
                    },
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        assert order == ["best", "mid", "worst"]

    def test_mixed_engines_top_card_shows_relevance_row(self, monkeypatch):
        """M2/R11 (CLI display): when a v2 collection is present, the top
        result's meta card surfaces a comparable 'Relevance' row (unified
        cosine measure) right after the raw 'Score' row, so v2's ~0.0-0.6
        cosine score is no longer uninterpretable next to v1's ~1.0-2.0
        squared-L2 distance."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "v1-coll": {
                "results": [
                    {
                        "id": "v1-doc",
                        "matchedChunks": [
                            {"score": 0.4, "content": {"indexedData": "v1 text"}}
                        ],
                    }
                ]
            },
            "v2-coll": {
                "scoreKind": "cosine",
                "results": [
                    {
                        "id": "v2-doc",
                        "matchedChunks": [
                            {"score": 0.5, "content": {"indexedData": "v2 text"}}
                        ],
                    }
                ],
            },
        }

        search_render.format_search_results("query", results=results, limit=5)

        text = record_console.export_text()
        assert "Relevance" in text
        assert "Score" in text
        # v1-doc (top): raw score 0.4 -> unified relevance 1 - 0.4/2 = 0.8000
        assert "0.8000" in text

    def test_v1_only_top_card_has_no_relevance_row(self, monkeypatch):
        """R6: a v1-only search (no scoreKind anywhere) renders EXACTLY as
        before the M2 feature — no 'Relevance' row/label anywhere in the
        rendered output."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "v1-coll": {
                "results": [
                    {
                        "id": "v1-doc",
                        "matchedChunks": [
                            {"score": 0.4, "content": {"indexedData": "v1 text"}}
                        ],
                    }
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        text = record_console.export_text()
        assert "Relevance" not in text
        assert "Score" in text

    def test_mixed_engines_compact_match_shows_rel_suffix(self, monkeypatch):
        """M2/R11 (CLI display): the compact 'Other matches' lines append the
        unified relevance (` / rel X.XXXX`) after the raw score, so v1 and v2
        rows can be compared visually."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            outputs.append(" ".join(str(a) for a in args))

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "v1-coll": {
                "results": [
                    {
                        "id": "v1-a",
                        "matchedChunks": [
                            {"score": 0.4, "content": {"indexedData": "a"}}
                        ],
                    },
                    {
                        "id": "v1-b",
                        "matchedChunks": [
                            {"score": 1.0, "content": {"indexedData": "b"}}
                        ],
                    },
                ]
            },
            "v2-coll": {
                "scoreKind": "cosine",
                "results": [
                    {
                        "id": "v2-a",
                        "matchedChunks": [
                            {"score": 0.3, "content": {"indexedData": "c"}}
                        ],
                    }
                ],
            },
        }

        search_render.format_search_results("query", results=results, limit=5)

        # Order: v1-a (rel .8, top card) > v1-b (rel .5) > v2-a (rel .3).
        v1_b_line = next(line for line in outputs if "v1-b" in line)
        v2_a_line = next(line for line in outputs if "v2-a" in line)
        assert "1.0000" in v1_b_line  # raw score unchanged
        assert "/ rel 0.5000" in v1_b_line
        assert "0.3000" in v2_a_line  # v2 raw score IS its relevance
        assert "/ rel 0.3000" in v2_a_line

    def test_v1_only_compact_match_has_no_rel_suffix(self, monkeypatch):
        """R6: a v1-only compact match line stays exactly as before — no
        ' / rel' suffix."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            outputs.append(" ".join(str(a) for a in args))

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "v1-coll": {
                "results": [
                    {
                        "id": "v1-a",
                        "matchedChunks": [
                            {"score": 0.4, "content": {"indexedData": "a"}}
                        ],
                    },
                    {
                        "id": "v1-b",
                        "matchedChunks": [
                            {"score": 1.0, "content": {"indexedData": "b"}}
                        ],
                    },
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        joined = "\n".join(outputs)
        assert "/ rel" not in joined

    def test_format_search_results_compact_handles_no_results(self, monkeypatch):
        """Compact formatter should also show a friendly message when empty."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        search_render.format_search_results_compact("query", results={})

        assert any("No results found" in line for line in outputs)

    def test_show_all_results_compact_groups_by_collection(self, monkeypatch):
        """_show_all_results_compact should group and count results per collection."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "coll1": {"results": [{"id": "a"}, {"id": "b"}]},
            "coll2": {"results": [{"id": "c"}]},
        }

        # Call the internal helper to keep behavior focused
        search_render._show_all_results_compact(results, limit=10)

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
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "coll1": {"results": [{"id": "doc1"}]},
        }

        search_render.format_search_results(
            "query", results=results, show_content=False
        )

        joined = "\n".join(outputs)
        # The compact path should list the collection
        assert "coll1" in joined

    def test_show_top_result_split_cards_non_dict_content(self, monkeypatch):
        """When chunk content is not a dict, it should be coerced to string."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            outputs.append(str(args))

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="doc1",
            path="/p",
            chunk={"score": 0.1, "content": "plain string content"},
            chunk_index=1,
        )
        # Should not raise even with string content
        search_render._show_top_result_split_cards(chunk_info)

    def test_show_compact_match_non_float_score(self, monkeypatch):
        """_show_compact_match with a non-float score should not raise."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        chunk_info = search_render.ChunkInfo(
            collection="col",
            doc_id="doc1",
            path="/p",
            chunk={"score": "high", "content": {"indexedData": "text"}},
            chunk_index=1,
        )
        search_render._show_compact_match(chunk_info)

        joined = "\n".join(outputs)
        assert "col" in joined
        assert "high" in joined

    def test_show_all_results_compact_skips_empty_but_surfaces_errors(
        self, monkeypatch
    ):
        """Empty (no-match) collections stay silently skipped, but a failed
        collection must be surfaced — not reported as a bare "no results"
        (foundation/6 E10, CLI twin of the MCP formatting bug)."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        with patch.object(search_render, "print_error") as mock_error:
            results: Dict[str, Any] = {
                "error-coll": {"error": "unavailable"},
                "empty-coll": {"results": []},
            }
            search_render._show_all_results_compact(results, limit=10)

        # The failed collection is reported via print_error, naming both the
        # collection and the underlying error.
        mock_error.assert_called_once()
        error_message = mock_error.call_args[0][0]
        assert "error-coll" in error_message
        assert "unavailable" in error_message

        joined = "\n".join(outputs)
        # empty-coll has no matches — stays silent, not a failure.
        assert "empty-coll" not in joined
        # A real failure must not be reported as a soft "no results found".
        assert "No results found" not in joined

    def test_top_result_skips_content_free_filename_chunk_for_real_content(
        self, monkeypatch
    ):
        """M1: chunk_number 0 is just the document's filename (e.g.
        'auth.py'), which can out-score real content for NL queries. The
        highlighted 'Best Matched' excerpt must skip such a content-free
        top-ranked chunk and show the next-best chunk with real content
        instead."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "coll1": {
                "results": [
                    {
                        "id": "src/auth_module.py",
                        "matchedChunks": [
                            {
                                "score": 0.1,
                                "content": {"indexedData": "src/auth_module.py"},
                            },
                            {
                                "score": 0.3,
                                "content": {
                                    "indexedData": "AUTH_MARKER: def authenticate(user, pw): ..."
                                },
                            },
                        ],
                    }
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        text = record_console.export_text()
        assert "AUTH_MARKER" in text
        # The excerpt panel body itself (not just the Document meta row)
        # must carry the real-content marker.
        excerpt_start = text.index("Top Result Excerpt")
        assert "AUTH_MARKER" in text[excerpt_start:]

    def test_top_result_falls_back_to_first_chunk_when_all_content_free(
        self, monkeypatch
    ):
        """If every candidate chunk is content-free (all filename-only), fall
        back to all_chunks[0] exactly as before the fix."""
        captured: Dict[str, Any] = {}

        monkeypatch.setattr(
            search_render,
            "_show_top_result_split_cards",
            lambda ci, **kw: captured.setdefault("top", ci),
        )
        monkeypatch.setattr(
            search_render, "_show_compact_match", lambda *_a, **_kw: None
        )
        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        results: Dict[str, Any] = {
            "coll1": {
                "results": [
                    {
                        "id": "src/auth.py",
                        "matchedChunks": [
                            {"score": 0.1, "content": {"indexedData": "src/auth.py"}},
                            {"score": 0.3, "content": {"indexedData": "auth.py"}},
                        ],
                    }
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        # Both candidates are content-free -> fall back to all_chunks[0]
        # (the first-ranked chunk, score 0.1).
        assert captured["top"]["chunk"]["score"] == 0.1

    def test_top_result_unchanged_when_content_absent(self, monkeypatch):
        """When matched-chunk content wasn't requested (no 'content' key at
        all), selection must be unchanged — still all_chunks[0] — since
        there's nothing to compare against the filename."""
        captured: Dict[str, Any] = {}

        monkeypatch.setattr(
            search_render,
            "_show_top_result_split_cards",
            lambda ci, **kw: captured.setdefault("top", ci),
        )
        monkeypatch.setattr(
            search_render, "_show_compact_match", lambda *_a, **_kw: None
        )
        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        results: Dict[str, Any] = {
            "coll1": {
                "results": [
                    {
                        "id": "src/auth.py",
                        "matchedChunks": [
                            {"score": 0.1},  # no content key at all
                            {"score": 0.3, "content": {"indexedData": "real text"}},
                        ],
                    }
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        assert captured["top"]["chunk"]["score"] == 0.1

    def test_other_matches_excludes_promoted_top(self, monkeypatch):
        """When a content-free #1 chunk causes some all_chunks[k] (k>=1) to
        be promoted to the highlighted top, "Other Matches" must NOT also
        show that same chunk — it must be excluded (by identity), not just a
        positional all_chunks[1:5] slice, which would duplicate it. "Other
        Matches" must also draw from the same content-free-filtered pool as
        the top pick (R5), so the content-free chunk itself never leaks into
        Other Matches either."""
        others: List[Any] = []
        monkeypatch.setattr(
            search_render, "_show_top_result_split_cards", lambda *a, **kw: None
        )
        monkeypatch.setattr(
            search_render,
            "_show_compact_match",
            lambda ci, **kw: others.append(ci["chunk"]["score"]),
        )
        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        results: Dict[str, Any] = {
            "coll1": {
                "results": [
                    {
                        "id": "src/auth.py",
                        "matchedChunks": [
                            {"score": 0.1, "content": {"indexedData": "src/auth.py"}},
                            {
                                "score": 0.3,
                                "content": {"indexedData": "real content b"},
                            },
                            {
                                "score": 0.5,
                                "content": {"indexedData": "real content c"},
                            },
                        ],
                    }
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        # all_chunks[0] (score 0.1) is content-free, so all_chunks[1] (score
        # 0.3) is promoted to the highlighted top. "Other Matches" must draw
        # from the SAME content-free-filtered pool as the top pick (R5), so
        # the content-free 0.1 chunk must never leak into either section —
        # only the remaining real-content chunk, 0.5, should show.
        assert others == [0.5]

    def test_other_matches_falls_back_to_all_chunks_when_all_content_free(
        self, monkeypatch
    ):
        """R5: when every chunk is content-free, "Other Matches" falls back
        to the unfiltered ``all_chunks`` pool (same fallback as the top
        pick) instead of ending up empty."""
        others: List[Any] = []
        monkeypatch.setattr(
            search_render, "_show_top_result_split_cards", lambda *a, **kw: None
        )
        monkeypatch.setattr(
            search_render,
            "_show_compact_match",
            lambda ci, **kw: others.append(ci["chunk"]["score"]),
        )
        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": lambda *a, **kw: None})()
        )

        results: Dict[str, Any] = {
            "coll1": {
                "results": [
                    {
                        "id": "src/auth.py",
                        "matchedChunks": [
                            {"score": 0.1, "content": {"indexedData": "src/auth.py"}},
                            {"score": 0.3, "content": {"indexedData": "auth.py"}},
                        ],
                    }
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        # Both chunks are content-free -> top falls back to all_chunks[0]
        # (score 0.1); "Other Matches" must fall back the same way and still
        # show the remaining chunk (score 0.3), not come up empty.
        assert others == [0.3]

    def test_rerank_score_kind_labels_top_result_score(self, monkeypatch):
        """R6: a result with scoreKind 'rerank' renders a distinguishing
        label on the rendered score, not indistinguishable from cosine."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "rerank-coll": {
                "scoreKind": "rerank",
                "results": [
                    {
                        "id": "rerank-doc",
                        "matchedChunks": [
                            {"score": 6.27, "content": {"indexedData": "real text"}}
                        ],
                    }
                ],
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        text = record_console.export_text()
        assert "6.2700 (rerank)" in text
        assert "(cosine)" not in text

    def test_cosine_score_kind_labels_compact_match_score(self, monkeypatch):
        """R6: a result with scoreKind 'cosine' renders its own label on the
        compact "Other Matches" score, not mislabeled as rerank."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            outputs.append(" ".join(str(a) for a in args))

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "cosine-coll": {
                "scoreKind": "cosine",
                "results": [
                    {
                        "id": "doc-a",
                        "matchedChunks": [
                            {"score": 0.9, "content": {"indexedData": "best"}}
                        ],
                    },
                    {
                        "id": "doc-b",
                        "matchedChunks": [
                            {"score": 0.3, "content": {"indexedData": "second"}}
                        ],
                    },
                ],
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        doc_b_line = next(line for line in outputs if "doc-b" in line)
        assert "0.3000 (cosine)" in doc_b_line
        assert "(rerank)" not in doc_b_line

    def test_rerank_and_cosine_score_kind_labels_not_cross_confused(self, monkeypatch):
        """R6: with a rerank collection and a cosine collection both present,
        each rendered score keeps its own label — a rerank score is never
        rendered with the cosine label, and vice versa."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "rerank-coll": {
                "scoreKind": "rerank",
                "results": [
                    {
                        "id": "rerank-doc",
                        "matchedChunks": [
                            {"score": 6.27, "content": {"indexedData": "rerank text"}}
                        ],
                    }
                ],
            },
            "cosine-coll": {
                "scoreKind": "cosine",
                "results": [
                    {
                        "id": "cosine-doc",
                        "matchedChunks": [
                            {"score": 0.5, "content": {"indexedData": "cosine text"}}
                        ],
                    }
                ],
            },
        }

        search_render.format_search_results("query", results=results, limit=5)

        text = record_console.export_text()
        # rerank's raw score (6.27) beats cosine's (0.5) on the unified
        # relevance measure, so rerank-doc is promoted to Top Result and
        # cosine-doc lands in Other Matches — split on that heading to check
        # each section carries only its own label.
        split_at = text.index("Other Search Query Matches")
        top_section = text[:split_at]
        others_section = text[split_at:]

        assert "(rerank)" in top_section
        assert "(cosine)" not in top_section
        assert "(cosine)" in others_section
        assert "(rerank)" not in others_section

    def test_v1_only_score_has_no_scale_label(self, monkeypatch):
        """R6: a v1-only search (no scoreKind anywhere) must not grow a
        scale label — score_kind_by_collection stays empty for it, so the
        label code must handle a missing/None scoreKind gracefully."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "v1-coll": {
                "results": [
                    {
                        "id": "v1-doc",
                        "matchedChunks": [
                            {"score": 0.4, "content": {"indexedData": "v1 text"}}
                        ],
                    }
                ]
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        text = record_console.export_text()
        assert "(cosine)" not in text
        assert "(rerank)" not in text

    def test_unsupported_score_kind_is_not_labeled_or_treated_higher_is_better(
        self, monkeypatch
    ):
        """R6: `V2Manifest.score_kind` is an unrestricted `str` — a malformed
        or future-versioned manifest could carry a value other than "cosine"/
        "rerank". That must never render as a trustworthy scale label, and
        must never be treated as higher-is-better (which would invert sort
        order for a scale nobody has actually validated) — it's dropped to
        the same "absent" state as a v1 collection instead."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "future-coll": {
                "scoreKind": "some-future-kind",
                "results": [
                    {
                        "id": "future-doc",
                        "matchedChunks": [
                            {"score": 0.4, "content": {"indexedData": "future text"}}
                        ],
                    }
                ],
            }
        }

        search_render.format_search_results("query", results=results, limit=5)

        text = record_console.export_text()
        assert "(some-future-kind)" not in text
        assert "(cosine)" not in text
        assert "(rerank)" not in text

    def test_compact_view_labels_rerank_score_kind(self, monkeypatch):
        """R6 (final-review I4): `index search --compact` routes through
        `format_search_results_compact`, which rendered a bare `[6.2700]` and
        never read `scoreKind`. It must carry the same label the meta card and
        `_show_compact_match` render."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "rerank-coll": {
                "scoreKind": "rerank",
                "results": [{"id": "rerank-doc", "score": 6.27}],
            }
        }

        search_render.format_search_results_compact("query", results=results, limit=10)

        text = record_console.export_text()
        assert "6.2700 (rerank)" in text
        assert "(cosine)" not in text

    def test_compact_view_labels_cosine_score_kind(self, monkeypatch):
        """R6 (final-review I4): the cosine label is not cross-confused with
        rerank on the `--compact` path either."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "cosine-coll": {
                "scoreKind": "cosine",
                "results": [{"id": "cosine-doc", "score": 0.3}],
            }
        }

        search_render.format_search_results_compact("query", results=results, limit=10)

        text = record_console.export_text()
        assert "0.3000 (cosine)" in text
        assert "(rerank)" not in text

    def test_compact_view_v1_score_has_no_scale_label(self, monkeypatch):
        """R6 byte-stability: a v1 collection carries no `scoreKind`, so the
        `--compact` line must stay exactly as it rendered before."""
        from rich.console import Console

        record_console = Console(record=True, width=100, no_color=True)
        monkeypatch.setattr(search_render, "console", record_console)

        results: Dict[str, Any] = {
            "v1-coll": {"results": [{"id": "v1-doc", "score": 0.75}]},
        }

        search_render.format_search_results_compact("query", results=results, limit=10)

        text = record_console.export_text()
        assert "v1-doc [0.7500]" in text
        assert "(cosine)" not in text
        assert "(rerank)" not in text

    def test_format_search_results_compact_with_results(self, monkeypatch):
        """format_search_results_compact should list docs with scores and show total."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "coll1": {
                "results": [
                    {"id": "doc-a", "score": 0.75},
                    {"id": "doc-b"},  # no score
                ]
            },
        }
        search_render.format_search_results_compact("query", results=results, limit=10)

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

    def test_search_named_collection_unavailable_exits_nonzero(self, monkeypatch):
        """A named collection whose status has no indexers (corrupt/unavailable)
        is a failed request, not a soft no-op — it must exit non-zero rather
        than the 0 a "search all, none searchable" fleet gets (foundation/6
        E1 same-theme gap)."""
        from unittest.mock import Mock

        broken_status = Mock()
        broken_status.name = "broken"
        broken_status.indexers = []  # no indexers => unavailable/corrupt

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [broken_status])
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)

        result = runner.invoke(search_cmd.app, ["my-query", "--collection", "broken"])

        assert result.exit_code != 0
        assert "No searchable collections available" in result.stdout

    def test_search_simple_named_collection_unavailable_exits_nonzero(
        self, monkeypatch
    ):
        """Same as above, but through the --simple-output JSON envelope path."""
        from unittest.mock import Mock

        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        broken_status = Mock()
        broken_status.name = "broken"
        broken_status.indexers = []

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [broken_status])
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)

        set_simple_output(True)
        try:
            result = runner.invoke(
                search_cmd.app, ["my-query", "--collection", "broken"]
            )

            assert result.exit_code != 0
            assert '"error": "No searchable collections available"' in result.stdout
        finally:
            reset_simple_output()

    def test_search_all_collections_runs_and_formats(self, monkeypatch):
        """Searching all collections should call svc_search and display results."""
        from unittest.mock import Mock, MagicMock

        statuses = [self._make_status("col1"), self._make_status("col2")]

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
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
            score_threshold=None,
            collections_path=None,
        ):
            return search_results

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

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
            score_threshold=None,
            collections_path=None,
        ):
            return {"myCol": {"results": [{"id": "d1", "score": 0.5}]}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

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
            score_threshold=None,
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
            score_threshold=None,
            collections_path=None,
        ):
            return {"col1": {"results": [{"id": "d1"}]}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

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

        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        statuses = [self._make_status("col1")]

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
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
            score_threshold=None,
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

        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [])
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
        """In simple output mode, a missing collection is reported as a JSON
        error envelope AND exits non-zero — a JSON error body must never look
        like success to a caller checking the exit code (foundation/6 E1)."""
        import json

        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [])
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)

        set_simple_output(True)
        try:
            result = runner.invoke(
                search_cmd.app, ["my-query", "--collection", "missing"]
            )

            assert result.exit_code != 0
            assert not isinstance(result.exception, IndexError)
            parsed = json.loads(result.stdout)
            assert "error" in parsed
            assert "missing" in parsed["error"]
        finally:
            reset_simple_output()


class TestSearchStatusMessages:
    """Tests verifying correct status/headline messages for search command."""

    def _make_status(self, name: str):
        from unittest.mock import Mock

        s = Mock()
        s.name = name
        s.indexers = ["default"]
        return s

    def test_single_collection_no_in_1_collection_headline(self, monkeypatch):
        """Single-collection search: no 'in 1 Collection:' headline, and the phase
        label (the only text the plain/non-Rich path shows) still carries the
        collection and query — not just a bare 'Searching outline'."""
        from unittest.mock import Mock

        statuses = [self._make_status("outline")]
        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: Mock())

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            score_threshold=None,
            collections_path=None,
        ):
            return {"outline": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        # FakePhased drops the title (like PlainPhasedProgress) and records the
        # start_phase labels — the regression surface for the plain-progress path.
        phase_labels: List[str] = []

        class FakePhased:
            def start_phase(self, label: str):
                phase_labels.append(label)

            def finish_phase(self, label: str):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            search_cmd, "create_phased_progress", lambda **kw: FakePhased()
        )

        result = runner.invoke(search_cmd.app, ["my-query", "--collection", "outline"])

        assert result.exit_code == 0
        assert "in 1 Collection:" not in result.stdout
        # Plain path shows only phase labels — they must carry collection + query.
        assert any(
            '"outline"' in lbl and "my-query" in lbl and "Collection for:" in lbl
            for lbl in phase_labels
        )

    def test_multi_collection_headline_contains_n_collections(self, monkeypatch):
        """Multi-collection search must print headline with N Collections and use per-collection phase labels."""
        from unittest.mock import Mock

        statuses = [self._make_status("col1"), self._make_status("col2")]
        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: Mock())

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            score_threshold=None,
            collections_path=None,
        ):
            return {"col1": {"results": []}, "col2": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        phase_labels: list = []

        class FakePhased:
            def start_phase(self, label: str):
                phase_labels.append(label)

            def finish_phase(self, label: str):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            search_cmd, "create_phased_progress", lambda **kw: FakePhased()
        )

        result = runner.invoke(search_cmd.app, ["my-query"])

        assert result.exit_code == 0
        assert "in 2 Collections:" in result.stdout
        assert any("col1" in lbl for lbl in phase_labels)
        assert any("col2" in lbl for lbl in phase_labels)

    def test_simple_output_no_status_lines(self, monkeypatch):
        """Simple (--simple) output mode must produce no status/headline lines."""
        import json
        from unittest.mock import Mock
        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        statuses = [self._make_status("col1")]
        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: Mock())

        def fake_svc_search(
            query,
            configs,
            max_docs,
            max_chunks,
            include_matched_chunks,
            score_threshold=None,
            collections_path=None,
        ):
            return {"col1": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        set_simple_output(True)
        try:
            result = runner.invoke(search_cmd.app, ["my-query"])

            assert result.exit_code == 0
            # Output must be valid JSON — no status lines mixed in
            parsed = json.loads(result.stdout)
            assert "query" in parsed
        finally:
            reset_simple_output()


class TestRerankFlag:
    """Tests for --rerank/--no-rerank on `index search` (core-v2-discoverability/2)."""

    def _make_status(self, name: str):
        from unittest.mock import Mock

        s = Mock()
        s.name = name
        s.indexers = ["default"]
        return s

    def _wire_common(self, monkeypatch, statuses):
        from unittest.mock import Mock, MagicMock

        monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
        monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
        monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)
        monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: Mock())

        phased_mock = MagicMock()
        phased_mock.__enter__ = Mock(return_value=phased_mock)
        phased_mock.__exit__ = Mock(return_value=False)
        monkeypatch.setattr(
            search_cmd, "create_phased_progress", lambda **kw: phased_mock
        )

    def test_search_help_shows_rerank_flag(self):
        """`index search --help` documents --rerank/--no-rerank *and* names
        the config key it overrides.

        The key must be written unbracketed (like --limit's
        ``core.v1.search.max_docs``): Rich parses ``[core.v2.rerank]`` as a
        markup tag and silently drops it, so a flag-name-only assertion
        passed while the one fact this help text carries was missing from
        the rendered output."""
        result = runner.invoke(search_cmd.app, ["--help"])

        assert result.exit_code == 0
        # The rich highlighter can style adjacent characters of a flag name
        # as separate spans (observed on CI's runners, not locally) — strip
        # ANSI so the assertion checks logical content, not exact styling.
        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "--rerank" in clean
        assert "--no-rerank" in clean
        assert "core.v2.rerank" in clean

    def test_flag_omitted_forwards_no_rerank_kwarg(self, monkeypatch):
        """No flag passed → identical to today: svc_search gets no 'rerank'
        kwarg at all (config alone decides, same as before this unit)."""
        self._wire_common(monkeypatch, [self._make_status("col1")])
        captured: Dict[str, Any] = {}

        def fake_svc_search(query, **kwargs):
            captured.update(kwargs)
            return {"col1": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        result = runner.invoke(search_cmd.app, ["my-query"])

        assert result.exit_code == 0
        assert "rerank" not in captured

    def test_rerank_flag_on_v2_collection_forwards_true_and_no_hint(self, monkeypatch):
        """--rerank on a v2 collection forwards rerank=True to svc_search and
        prints no v1-no-effect hint (at least one searched collection is v2)."""
        self._wire_common(monkeypatch, [self._make_status("v2col")])
        monkeypatch.setattr(
            "indexed.core.versioning.detect_engine_version", lambda path: "2"
        )
        captured: Dict[str, Any] = {}

        def fake_svc_search(query, **kwargs):
            captured.update(kwargs)
            return {"v2col": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        result = runner.invoke(search_cmd.app, ["my-query", "--rerank"])

        assert result.exit_code == 0
        assert captured.get("rerank") is True
        assert "no effect" not in result.stdout

    def test_no_rerank_flag_forwards_false(self, monkeypatch):
        """--no-rerank explicitly forwards rerank=False (disables even a
        config with enabled=true) and never prints the no-effect hint."""
        self._wire_common(monkeypatch, [self._make_status("col1")])
        captured: Dict[str, Any] = {}

        def fake_svc_search(query, **kwargs):
            captured.update(kwargs)
            return {"col1": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        result = runner.invoke(search_cmd.app, ["my-query", "--no-rerank"])

        assert result.exit_code == 0
        assert captured.get("rerank") is False
        assert "no effect" not in result.stdout

    def test_rerank_on_v1_only_search_prints_hint_and_does_not_crash(self, monkeypatch):
        """--rerank passed explicitly, all searched collections resolve to
        v1 → no crash, and a one-line hint is printed (never a silent
        no-op), resolved via detect_engine_version per searched collection."""
        self._wire_common(monkeypatch, [self._make_status("v1col")])
        monkeypatch.setattr(
            "indexed.core.versioning.detect_engine_version", lambda path: "1"
        )
        captured: Dict[str, Any] = {}

        def fake_svc_search(query, **kwargs):
            captured.update(kwargs)
            return {"v1col": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        result = runner.invoke(search_cmd.app, ["my-query", "--rerank"])

        assert result.exit_code == 0
        assert captured.get("rerank") is True
        assert "no effect" in result.stdout
        assert "v2-only" in result.stdout

    def test_rerank_v1_only_simple_output_stays_clean_json(self, monkeypatch):
        """--rerank on an all-v1 fleet under --simple-output must NOT print
        the Rich info panel: stdout there is a JSON envelope
        (simple_output.py's contract), so the hint would otherwise break
        json.loads() for any programmatic consumer (review finding #1)."""
        import json

        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        self._wire_common(monkeypatch, [self._make_status("v1col")])
        detect_calls: List[Any] = []
        monkeypatch.setattr(
            "indexed.core.versioning.detect_engine_version",
            lambda path: detect_calls.append(path) or "1",
        )

        def fake_svc_search(query, **kwargs):
            return {
                "v1col": {
                    "results": [
                        {
                            "id": "doc1",
                            "matchedChunks": [{"chunkNumber": 0, "score": 0.1}],
                        }
                    ]
                }
            }

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        set_simple_output(True)
        try:
            result = runner.invoke(search_cmd.app, ["my-query", "--rerank"])

            assert result.exit_code == 0
            # Must parse as JSON outright — a leaked info panel above the
            # JSON body would make this raise.
            parsed = json.loads(result.stdout)
            assert parsed["query"] == "my-query"
            # The hint text must be nowhere in stdout, not even alongside
            # valid JSON.
            assert "no effect" not in result.stdout
            # The all-v1-fleet check DOES still run in simple mode — the
            # notice is merely rerouted to stderr (R2: never a silent
            # no-op, on any surface), so detection must have happened.
            assert detect_calls
        finally:
            reset_simple_output()

    def test_rerank_v1_only_simple_output_emits_notice_on_stderr(self, monkeypatch):
        """R2's "never a silent no-op" holds for --simple-output too: the
        one-line notice is written to STDERR, keeping stdout a pure JSON
        envelope while the machine-readable surface — the one an agent or
        script is most likely to drive — still says the flag did nothing."""
        import json

        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        self._wire_common(monkeypatch, [self._make_status("v1col")])
        monkeypatch.setattr(
            "indexed.core.versioning.detect_engine_version", lambda path: "1"
        )

        def fake_svc_search(query, **kwargs):
            return {"v1col": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        set_simple_output(True)
        try:
            result = runner.invoke(search_cmd.app, ["my-query", "--rerank"])

            assert result.exit_code == 0
            # stdout: still pure JSON, with no notice text in it.
            json.loads(result.stdout)
            assert "no effect" not in result.stdout
            # stderr: carries the notice, as one plain line (no Rich panel
            # borders — the shared `console` is bound to stdout).
            assert "no effect" in result.stderr
            assert "v2-only" in result.stderr
            assert "╭" not in result.stderr
        finally:
            reset_simple_output()

    def test_rerank_on_mixed_v1_v2_search_prints_no_hint(self, monkeypatch):
        """--rerank on a search spanning one v1 and one v2 collection prints
        no hint — the flag DID apply, to the v2 collection."""
        self._wire_common(
            monkeypatch, [self._make_status("v1col"), self._make_status("v2col")]
        )

        def fake_detect(path):
            return "2" if path.name == "v2col" else "1"

        monkeypatch.setattr(
            "indexed.core.versioning.detect_engine_version", fake_detect
        )

        def fake_svc_search(query, **kwargs):
            return {"v1col": {"results": []}, "v2col": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        result = runner.invoke(search_cmd.app, ["my-query", "--rerank"])

        assert result.exit_code == 0
        assert "no effect" not in result.stdout

    def test_rerank_none_default_prints_no_hint_even_if_v1_only(self, monkeypatch):
        """Flag omitted (rerank stays None) → no hint at all, even against
        an all-v1 fleet — the hint is only for an explicit, defeated --rerank."""
        self._wire_common(monkeypatch, [self._make_status("v1col")])
        detect_calls = []
        monkeypatch.setattr(
            "indexed.core.versioning.detect_engine_version",
            lambda path: detect_calls.append(path) or "1",
        )

        def fake_svc_search(query, **kwargs):
            return {"v1col": {"results": []}}

        monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)

        result = runner.invoke(search_cmd.app, ["my-query"])

        assert result.exit_code == 0
        assert "no effect" not in result.stdout
        # detect_engine_version is only invoked when rerank is True.
        assert detect_calls == []


class TestFormatSearchResultsCompactEdgeCases:
    """Tests for edge cases in compact formatter."""

    def test_compact_skips_error_collections(self, monkeypatch):
        """format_search_results_compact excludes error collections from the
        results listing, but must still surface the failure (foundation/6
        E10, CLI twin of the MCP formatting bug)."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        with patch.object(search_render, "print_error") as mock_error:
            results: Dict[str, Any] = {
                "error-coll": {"error": "unavailable"},
                "good-coll": {"results": [{"id": "doc1", "score": 0.5}]},
            }
            search_render.format_search_results_compact("query", results=results)

        joined = "\n".join(outputs)
        assert "error-coll" not in joined
        assert "good-coll" in joined

        mock_error.assert_called_once()
        error_message = mock_error.call_args[0][0]
        assert "error-coll" in error_message
        assert "unavailable" in error_message

    def test_compact_skips_empty_collections(self, monkeypatch):
        """format_search_results_compact should skip collections with no results."""
        outputs: List[str] = []

        def fake_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            outputs.append(text)

        monkeypatch.setattr(
            search_render, "console", type("C", (), {"print": fake_print})()
        )

        results: Dict[str, Any] = {
            "empty-coll": {"results": []},
        }
        search_render.format_search_results_compact("query", results=results)

        joined = "\n".join(outputs)
        assert "empty-coll" not in joined
        assert "No results found" in joined
