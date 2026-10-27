"""Golden-output test for the ONE documented search shape (`indexed.search/1`).

Three surfaces must emit byte-identical payloads from one builder:

1. ``indexed.mcp.formatting.build_search_payload`` — the builder itself;
2. the MCP tools ``search`` / ``search_collection`` — what an agent receives;
3. ``indexed search --json`` (and its legacy alias ``--simple-output``) — what
   a shell, a script or an agent's Bash tool receives.

The expected payload is HAND-WRITTEN in ``golden/search_payload.json``, not
generated from the implementation: it is the contract, so a behaviour change
has to disagree with a file a human wrote (issues #108/#109).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from typer.testing import CliRunner

import indexed.mcp.server as server_module
import indexed.mcp.tools as tools_module
from indexed.cli.knowledge.commands import search as search_cmd
from indexed.mcp.formatting import build_search_payload

pytestmark = pytest.mark.unit

GOLDEN = Path(__file__).parent / "golden" / "search_payload.json"
QUERY = "how is relevance unified across engines"

#: The raw core result the golden payload is built from: one v1 collection
#: (squared-L2, code + Markdown chunks) and one v2 collection (cosine, Outline
#: document). Between them they cover every locator kind the shape emits
#: except ``document``, which has its own unit test in ``test_formatting``.
RAW_RESULTS = {
    "indexed-src": {
        "collectionName": "indexed-src",
        "indexerName": "e5-small",
        "sourceType": "localFiles",
        "results": [
            {
                "id": "src/indexed/utils/relevance.py",
                "url": "file:///repo/src/indexed/utils/relevance.py",
                "matchedChunks": [
                    {
                        "chunkNumber": 1,
                        "score": 0.75,
                        "content": {
                            "indexedData": 'HIGHER_IS_BETTER = frozenset({"cosine", "rerank"})',
                            "metadata": {
                                "language": "python",
                                "node_type": "module",
                                "start_line": 17,
                                "end_line": 18,
                                "file_path": "/repo/src/indexed/utils/relevance.py",
                            },
                        },
                    },
                    {
                        "chunkNumber": 2,
                        "score": 0.25,
                        "content": {
                            "indexedData": (
                                "# /repo/src/indexed/utils/relevance.py\n"
                                "def unified_relevance(raw_score, score_kind):\n"
                                "    return 1.0\n"
                            ),
                            "metadata": {
                                "language": "python",
                                "node_type": "function_definition",
                                "start_line": 20,
                                "end_line": 38,
                                "file_path": "/repo/src/indexed/utils/relevance.py",
                            },
                        },
                    },
                ],
            },
            {
                "id": "docs/search.md",
                "url": "file:///repo/docs/search.md",
                "matchedChunks": [
                    {
                        "chunkNumber": 2,
                        "score": 1.5,
                        "content": {
                            "indexedData": (
                                "## Output shape\n\n"
                                "Agents get one payload, documents grouped."
                            ),
                            "metadata": {"headings": ["Search", "Output shape"]},
                        },
                    }
                ],
            },
        ],
    },
    "notes-v2": {
        "collectionName": "notes-v2",
        "indexerName": "bge-m3",
        "sourceType": "outline",
        "scoreKind": "cosine",
        "results": [
            {
                "id": "page-42",
                "url": "https://outline.example/page-42",
                "matchedChunks": [
                    {
                        "chunkNumber": 3,
                        "score": 0.91,
                        "content": {
                            "indexedData": (
                                "Reranking replaces the cosine score with a "
                                "cross-encoder logit."
                            ),
                            "metadata": {
                                "headings": ["Rerank", "Cross-engine relevance"],
                                "src_meta": {"sourceId": "page-42"},
                            },
                        },
                    }
                ],
            }
        ],
    },
}


def _golden() -> dict:
    return json.loads(GOLDEN.read_text())


def test_builder_matches_the_golden_payload() -> None:
    """The builder's output must equal the hand-written golden file exactly —
    including key order, so the documented shape cannot drift silently."""
    payload = build_search_payload(RAW_RESULTS, QUERY)

    assert payload == _golden()
    assert json.dumps(payload, indent=2) + "\n" == GOLDEN.read_text()


# --- surface 2: the MCP tool -------------------------------------------------


def _mcp_search_tool():
    return asyncio.run(server_module.mcp.get_tool("search"))


def test_mcp_search_tool_returns_the_golden_payload() -> None:
    search_cfg = MagicMock()
    search_cfg.max_docs = 10
    search_cfg.max_chunks = 30
    search_cfg.score_threshold = None
    search_cfg.include_full_text = False
    search_cfg.include_all_chunks = False
    search_cfg.include_matched_chunks = True

    with (
        patch.object(tools_module, "svc_search", return_value=RAW_RESULTS),
        patch.object(server_module, "_get_config", return_value=search_cfg),
    ):
        payload = _mcp_search_tool().fn(QUERY)

    assert payload == _golden()


# --- surface 3: the CLI ------------------------------------------------------

runner = CliRunner()


@pytest.fixture(autouse=True)
def _patch_runtime_context():
    mock_config = MagicMock()
    mock_config.resolve_storage_mode.return_value = "global"
    mock_config.get_workspace_preference.return_value = None
    mock_config.store.read.return_value = {}
    ctx = type(
        "MockCtx",
        (),
        {
            "collections_path": Path("/tmp/test-collections"),
            "mode": "global",
            "config_service": mock_config,
        },
    )()
    with (
        patch(
            "indexed.cli.composition.resolve_collections_context",
            side_effect=lambda *args, **kwargs: ctx,
        ),
        patch(
            "indexed.cli.utils.storage_info.display_storage_mode_for_command",
            lambda *args, **kwargs: None,
        ),
    ):
        yield


def _patch_search_command(monkeypatch) -> None:
    statuses = []
    for name in RAW_RESULTS:
        status = Mock()
        status.name = name
        status.indexers = ["default"]
        statuses.append(status)

    def fake_svc_search(query, configs, **_kwargs):
        return RAW_RESULTS

    monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: statuses)
    monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)
    monkeypatch.setattr(search_cmd, "setup_root_logger", lambda **kw: None)
    monkeypatch.setattr(search_cmd, "is_verbose_mode", lambda: False)
    monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: Mock())


def test_cli_json_flag_emits_the_golden_payload(monkeypatch) -> None:
    _patch_search_command(monkeypatch)

    result = runner.invoke(search_cmd.app, [QUERY, "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == _golden()


def test_cli_simple_output_alias_emits_the_same_payload(monkeypatch) -> None:
    """``--simple-output`` is the legacy alias of ``--json``; one shape, not two."""
    from indexed.cli.utils.simple_output import reset_simple_output, set_simple_output

    _patch_search_command(monkeypatch)
    set_simple_output(True)
    try:
        result = runner.invoke(search_cmd.app, [QUERY])
    finally:
        reset_simple_output()

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == _golden()


def test_cli_json_stdout_is_parseable_with_no_human_chrome(monkeypatch) -> None:
    """Nothing an agent must strip: stdout is the JSON document and nothing else."""
    _patch_search_command(monkeypatch)

    result = runner.invoke(search_cmd.app, [QUERY, "--json"])

    assert result.stdout.strip().startswith("{")
    assert result.stdout.rstrip().endswith("}")
    assert "indexed.search/1" in result.stdout
