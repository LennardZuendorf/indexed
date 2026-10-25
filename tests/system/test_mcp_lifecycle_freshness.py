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
NEW_COLLECTION = "mcp-lifecycle-new"
NEEDLE_A = "penguin migration survey along the Antarctic coastline"
NEEDLE_B = "walrus haul-out census across the Bering shelf"
NEEDLE_NEW = "heron rookery census along the tidal marsh"
NEEDLE_RECREATED = "orca pod tracking across the fjord"


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


def _invoke(args: list[str]) -> None:
    result = runner.invoke(app, ["--local", "--log-level", "ERROR", *args])
    assert result.exit_code == 0, result.stdout + result.stderr


def _create(
    ws, corpus: Path, *, force: bool = False, collection: str = COLLECTION
) -> None:
    args = [
        "--engine",
        "v2",
        "create",
        "files",
        "--collection",
        collection,
        "--path",
        str(corpus),
        "--local",
        "--no-cache",
    ]
    if force:
        args.append("--force")
    _invoke(args)


def _remove(collection: str) -> None:
    _invoke(["remove", collection, "--force"])


def _disk(collection: str) -> dict:
    result = runner.invoke(
        app,
        ["--local", "--simple-output", "--log-level", "ERROR", "inspect", collection],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


async def _resource(session, uri: str) -> dict:
    result = await session.read_resource(uri)
    return json.loads(result.contents[0].text)


def _status(payload: dict, name: str) -> dict | None:
    return next((c for c in payload["collections"] if c["name"] == name), None)


def _texts(payload: dict) -> str:
    return " ".join(r["text"].lower() for r in payload.get("results") or [])


async def _lifecycle(
    ws,
    corpus_a: Path,
    corpus_b: Path,
    corpus_new: Path,
    corpus_recreated: Path,
) -> dict:
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

            # A NEW collection appears on disk while the server lives.
            await asyncio.to_thread(_create, ws, corpus_new, collection=NEW_COLLECTION)
            new_list = await _resource(session, "resource://collections")
            new_status = await _resource(session, "resource://collections/status")
            new_disk = await asyncio.to_thread(_disk, NEW_COLLECTION)
            new_search = _extract_payload(
                await session.call_tool(
                    "search_collection",
                    {"collection": NEW_COLLECTION, "query": NEEDLE_NEW},
                )
            )

            # Removing it must make it unknown, not silently empty.
            await asyncio.to_thread(_remove, NEW_COLLECTION)
            gone_list = await _resource(session, "resource://collections")
            gone_status = await _resource(session, "resource://collections/status")
            gone_search = _extract_payload(
                await session.call_tool(
                    "search_collection",
                    {"collection": NEW_COLLECTION, "query": NEEDLE_NEW},
                )
            )

            # Re-creating the same name with different content must win.
            await asyncio.to_thread(
                _create, ws, corpus_recreated, collection=NEW_COLLECTION
            )
            recreated_list = await _resource(session, "resource://collections")
            recreated_status = await _resource(session, "resource://collections/status")
            recreated_disk = await asyncio.to_thread(_disk, NEW_COLLECTION)
            recreated_search = _extract_payload(
                await session.call_tool(
                    "search_collection",
                    {"collection": NEW_COLLECTION, "query": NEEDLE_RECREATED},
                )
            )
            stale_search = _extract_payload(
                await session.call_tool(
                    "search_collection",
                    {"collection": NEW_COLLECTION, "query": NEEDLE_NEW},
                )
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
    return {
        "before": before,
        "after": after,
        "new_list": new_list,
        "new_status": new_status,
        "new_disk": new_disk,
        "new_search": new_search,
        "gone_list": gone_list,
        "gone_status": gone_status,
        "gone_search": gone_search,
        "recreated_list": recreated_list,
        "recreated_status": recreated_status,
        "recreated_disk": recreated_disk,
        "recreated_search": recreated_search,
        "stale_search": stale_search,
        "single": single,
        "every": every,
    }


def test_one_long_lived_process_tracks_rebuild_then_corruption(
    local_workspace, tmp_path: Path
) -> None:
    ws = local_workspace
    (ws.local_root / "config.toml").touch()
    corpora = (
        _corpus(tmp_path, "corpus-a", NEEDLE_A),
        _corpus(tmp_path, "corpus-b", NEEDLE_B),
        _corpus(tmp_path, "corpus-new", NEEDLE_NEW),
        _corpus(tmp_path, "corpus-recreated", NEEDLE_RECREATED),
    )
    payload = asyncio.run(_lifecycle(ws, *corpora))

    # 1. freshness: the same process answers from the rebuilt index.
    assert payload["before"]["results"], f"initial search empty: {payload!r}"
    assert "penguin" in payload["before"]["results"][0]["text"].lower()
    texts = " ".join(r["text"].lower() for r in payload["after"].get("results") or [])
    assert payload["after"]["results"], f"post-rebuild search empty: {payload!r}"
    assert "walrus" in texts, f"same process served a stale index: {payload!r}"
    assert "penguin" not in texts, f"served pre-rebuild content: {payload!r}"

    # 2. a collection created after startup is visible through the live process.
    assert NEW_COLLECTION in payload["new_list"]["collections"], payload
    new = _status(payload["new_status"], NEW_COLLECTION)
    assert new, payload
    for key in ("number_of_documents", "number_of_chunks"):
        assert new[key] > 0, payload
        assert new[key] == payload["new_disk"][key], payload
    assert "heron" in _texts(payload["new_search"]), payload

    # 3. removal is an explicit unknown-collection error, never an empty hit.
    assert NEW_COLLECTION not in payload["gone_list"]["collections"], payload
    assert _status(payload["gone_status"], NEW_COLLECTION) is None, payload
    assert "error" in payload["gone_search"], payload
    assert "results" not in payload["gone_search"], payload
    assert "not found" in payload["gone_search"]["error"].lower(), payload

    # 4. re-creation serves the new content, not the removed content.
    assert NEW_COLLECTION in payload["recreated_list"]["collections"], payload
    recreated = _status(payload["recreated_status"], NEW_COLLECTION)
    assert recreated, payload
    for key in ("number_of_documents", "number_of_chunks"):
        assert recreated[key] == payload["recreated_disk"][key], payload
    assert "orca" in _texts(payload["recreated_search"]), payload
    assert "heron" not in _texts(payload["recreated_search"]), payload
    assert "heron" not in _texts(payload["stale_search"]), payload

    # 5. corruption is a failure, not a miss and not a typo hint.
    assert "error" in payload["single"], payload
    assert "not found" not in str(payload["single"]["error"]).lower()
    errors = payload["every"].get("collection_errors") or []
    assert any(e.get("collection") == COLLECTION for e in errors), payload
    # partial success: the healthy sibling's hits survive the corrupt collection,
    # and nothing claims to come from the collection that could not be opened.
    assert payload["every"]["results"], payload
    assert {r["collection"] for r in payload["every"]["results"]} == {NEW_COLLECTION}, (
        payload
    )
