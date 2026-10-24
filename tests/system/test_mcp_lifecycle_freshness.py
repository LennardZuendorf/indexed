"""Lifecycle regression: one long-lived MCP process vs. on-disk changes (#112/#125).

Drives the real out-of-process stdio server (an in-process client SEGFAULTS with
llama-index + torch) and asserts what an agent can observe through one process:
an external rebuild is picked up without a restart, and a collection that becomes
unreadable is reported as a failure — never "unknown collection", never silence.
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

COLLECTION = "mcp-lifecycle"
NEEDLE_A = "penguin migration survey along the Antarctic coastline"
NEEDLE_B = "walrus haul-out census across the Bering shelf"


def _extract_payload(result) -> dict:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no parseable payload in MCP result: {result!r}")


def _corpus(root: Path, name: str, needle: str) -> Path:
    corpus = root / name
    corpus.mkdir()
    (corpus / "needle.txt").write_text(f"# Survey\n\n{needle}\n")
    (corpus / "notes.txt").write_text("# Notes\n\nField logistics and staffing.\n")
    return corpus


def _create(ws, corpus: Path, *, force: bool = False) -> None:
    args = [
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
        str(corpus),
        "--local",
        "--no-cache",
    ]
    if force:
        args.append("--force")
    created = runner.invoke(app, args)
    assert created.exit_code == 0, created.stdout + created.stderr


async def _lifecycle(ws, corpus_a: Path, corpus_b: Path) -> dict[str, dict]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "indexed.mcp.cli", "run", "--no-banner"],
        cwd=str(ws.root),
        env={**os.environ, "TQDM_DISABLE": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=180)
        ) as session:
            await session.initialize()
            await asyncio.to_thread(_create, ws, corpus_a)
            before = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_A})
            )

            # Externally rebuild the SAME collection name while the server lives.
            await asyncio.to_thread(_create, ws, corpus_b, force=True)
            manifest = ws.collections_dir / COLLECTION / "manifest.json"
            assert json.loads(manifest.read_text())["version"] == "2"
            after = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_B})
            )

            # The index exists on disk but its manifest is now unreadable.
            manifest.write_text("{ not json")
            single = _extract_payload(
                await session.call_tool(
                    "search_collection", {"collection": COLLECTION, "query": NEEDLE_B}
                )
            )
            every = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_B})
            )
    return {"before": before, "after": after, "single": single, "every": every}


def test_one_long_lived_process_tracks_rebuild_then_corruption(
    local_workspace, tmp_path: Path
) -> None:
    ws = local_workspace
    (ws.local_root / "config.toml").touch()
    corpora = (
        _corpus(tmp_path, "corpus-a", NEEDLE_A),
        _corpus(tmp_path, "corpus-b", NEEDLE_B),
    )
    payload = asyncio.run(_lifecycle(ws, *corpora))

    # 1. freshness: the same process answers from the rebuilt index.
    assert payload["before"]["results"], f"initial search empty: {payload!r}"
    assert "penguin" in payload["before"]["results"][0]["text"].lower()
    texts = " ".join(r["text"].lower() for r in payload["after"].get("results") or [])
    assert payload["after"]["results"], f"post-rebuild search empty: {payload!r}"
    assert "walrus" in texts, f"same process served a stale index: {payload!r}"
    assert "penguin" not in texts, f"served pre-rebuild content: {payload!r}"

    # 2. corruption is a failure, not a miss and not a typo hint.
    assert "error" in payload["single"], payload
    assert "not found" not in str(payload["single"]["error"]).lower()
    errors = payload["every"].get("collection_errors") or []
    assert any(e.get("collection") == COLLECTION for e in errors), payload
    assert payload["every"]["results"] == [], payload
