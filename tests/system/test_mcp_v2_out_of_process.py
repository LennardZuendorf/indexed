"""System smoke: MCP v2 search driven OUT-OF-PROCESS over real stdio
(core-v2/8, R4 + tech.md "MCP: v2 e2e MUST run out-of-process").

The in-process FastMCP client + llama-index + torch SEGFAULTS (exit 139 —
verified in PR #86 and recorded in tech.md/research.md), so this test spawns the
real ``indexed-mcp`` server as a SEPARATE subprocess over stdio and drives one
v2 search through it with the low-level ``mcp`` stdio client. It is a smoke test
by design: one round trip proving a v2 collection is searchable through the
agent-facing MCP surface end to end.

Storage: the server subprocess runs with ``cwd`` at the temp workspace whose
``.indexed/config.toml`` makes it auto-detect LOCAL mode, so it reads the same
collections dir the in-process create wrote to — no ``$HOME`` override, so the
shared HuggingFace model cache resolves normally (offline, no download).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from tests.conftest import model_available

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "mcp-v2-net"
NEEDLE_QUERY = "penguin migration survey along the Antarctic coastline"


def _extract_payload(result) -> dict:
    """Pull the tool's dict result out of an MCP ``CallToolResult``."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps a bare dict return under a "result" key when it is not a
        # declared object schema; unwrap either shape.
        return structured.get("result", structured)
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no parseable payload in MCP result: {result!r}")


async def _drive_mcp_search(workspace_root: Path) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "indexed.mcp.cli", "run", "--no-banner"],
        cwd=str(workspace_root),
        env={**os.environ, "TQDM_DISABLE": "1"},
    )
    # Generous read timeout: the FIRST v2 search loads the embedding model in the
    # server subprocess (a few seconds), well within this bound.
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=120)
        ) as session:
            await session.initialize()
            result = await session.call_tool("search", {"query": NEEDLE_QUERY})
    return _extract_payload(result)


def test_mcp_v2_search_out_of_process(local_workspace, files_corpus: Path) -> None:
    ws = local_workspace

    # ``.indexed/config.toml`` present → the server subprocess (cwd = ws.root)
    # auto-detects LOCAL mode and reads this same collections dir.
    (ws.local_root / "config.toml").touch()

    # Create the v2 collection in-process (fast); the subprocess only reads it.
    created = runner.invoke(
        app,
        [
            "--engine",
            "v2",
            "--local",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--collection",
            COLLECTION,
            "--path",
            str(files_corpus),
            "--local",
            "--no-cache",
        ],
    )
    assert created.exit_code == 0, created.stdout + created.stderr
    manifest = json.loads(
        (ws.collections_dir / COLLECTION / "manifest.json").read_text()
    )
    assert manifest["version"] == "2", "collection must be a v2 collection"

    payload = asyncio.run(_drive_mcp_search(ws.root))

    results = payload.get("results") or []
    assert results, f"MCP v2 search returned no results: {payload!r}"
    top = results[0]
    assert top["document_id"].endswith("needle.txt"), (
        f"expected needle.txt as top MCP v2 hit, got {top['document_id']!r}"
    )
    assert top["collection"] == COLLECTION
    assert "penguin" in top["text"].lower()
