"""Live proof: the MCP server keeps ``localFiles`` collections fresh (#67 slice 2).

Drives the real out-of-process stdio server. With ``[mcp] watch_enabled = true``
a file written into the collection's source tree becomes searchable through the
*same* session — no ``index update``, no restart. With the gate off nothing is
watched, and a collection created while the server runs is only watched after
the next restart (startup determines the scope).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
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

COLLECTION = "mcp-watch"
COLLECTION_LATE = "mcp-watch-late"
NEEDLE_A = "penguin migration survey along the Antarctic coastline"
NEEDLE_B = "walrus haul-out census across the Bering shelf"
NEEDLE_LATE = "heron rookery census along the tidal marsh"
NEEDLE_LATE_EDIT = "orca pod tracking across the fjord"
SEARCH_DEADLINE_S = 120.0
NO_WATCH_WINDOW_S = 6.0


def _extract_payload(result) -> dict:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no parseable payload in MCP result: {result!r}")


def _hits(payload: dict) -> list[dict]:
    return [hit for doc in payload.get("documents") or [] for hit in doc["hits"]]


def _texts(payload: dict) -> str:
    return " ".join(hit["text"].lower() for hit in _hits(payload))


def _corpus(root: Path, name: str, needle: str) -> Path:
    corpus = root / name
    corpus.mkdir()
    (corpus / "needle.txt").write_text(f"# Survey\n\n{needle}\n")
    (corpus / "notes.txt").write_text("# Notes\n\nField logistics and staffing.\n")
    return corpus


def _write_config(ws, *, watch_enabled: bool) -> None:
    """Point the local workspace config at the watcher gate under test."""
    (ws.local_root / "config.toml").write_text(
        "[_meta]\n"
        'schema_version = "1"\n'
        "\n[mcp]\n"
        f"watch_enabled = {str(watch_enabled).lower()}\n"
        "watch_debounce_seconds = 0.2\n"
        "watch_poll_interval_seconds = 0.1\n"
    )


def _invoke(args: list[str]) -> None:
    result = runner.invoke(app, ["--local", "--log-level", "ERROR", *args])
    assert result.exit_code == 0, result.stdout + result.stderr


def _create(corpus: Path, *, collection: str, engine: str = "v2") -> None:
    _invoke(
        [
            "--engine",
            engine,
            "create",
            "files",
            "--collection",
            collection,
            "--path",
            str(corpus),
            "--local",
            "--no-cache",
        ]
    )


def _server_params(ws):
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "indexed.mcp.cli", "run", "--no-banner"],
        cwd=str(ws.root),
        env={**os.environ, "TQDM_DISABLE": "1"},
    )


async def _wait_for_text(session, needle: str, *, deadline_s: float) -> dict:
    """Poll the live session until its results mention ``needle``."""
    deadline = time.monotonic() + deadline_s
    last: dict = {}
    while time.monotonic() < deadline:
        try:
            last = _extract_payload(
                await session.call_tool("search", {"query": needle})
            )
        except Exception as exc:  # noqa: BLE001 — the index dir swaps mid-update
            last = {"transient_error": str(exc)}
        if needle.split()[0] in _texts(last):
            return last
        await asyncio.sleep(0.5)
    raise AssertionError(f"{needle!r} never became searchable; last payload: {last!r}")


async def _freshness(ws, corpus: Path) -> dict:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params(ws)) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=180)
        ) as session:
            await session.initialize()
            # Let the watcher's opening catch-up pass finish before the edit.
            await asyncio.sleep(3.0)
            before = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_A})
            )
            (corpus / "delta.txt").write_text(
                "The volcanic sulfur survey found deposits near the caldera rim "
                "and the walrus haul-out census across the Bering shelf.\n"
            )
            after = await _wait_for_text(
                session, NEEDLE_B, deadline_s=SEARCH_DEADLINE_S
            )
    return {"before": before, "after": after}


@pytest.mark.parametrize("engine", ["v1", "v2"])
def test_live_edit_becomes_searchable_without_a_restart(
    local_workspace, tmp_path: Path, engine: str
) -> None:
    ws = local_workspace
    _write_config(ws, watch_enabled=True)
    corpus = _corpus(tmp_path, "corpus", NEEDLE_A)
    _create(corpus, collection=COLLECTION, engine=engine)

    payload = asyncio.run(_freshness(ws, corpus))

    assert "penguin" in _texts(payload["before"]), payload["before"]
    assert "walrus" in _texts(payload["after"]), (
        "the watched file was never indexed into the served collection: "
        f"{payload['after']!r}"
    )
    assert (ws.collections_dir / COLLECTION).is_dir()


async def _gated_sessions(ws, corpus_a: Path, corpus_late: Path) -> dict:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params(ws)) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=180)
        ) as session:
            await session.initialize()
            await asyncio.sleep(3.0)
            before = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_A})
            )
            (corpus_a / "delta.txt").write_text(
                f"The volcanic sulfur survey found deposits near the caldera rim. "
                f"Also: {NEEDLE_B}.\n"
            )
            # A collection created after startup is outside this server's scope.
            await asyncio.to_thread(_create, corpus_late, collection=COLLECTION_LATE)
            (corpus_late / "delta.txt").write_text(
                f"# Late edit\n\n{NEEDLE_LATE_EDIT}\n"
            )
            await asyncio.sleep(NO_WATCH_WINDOW_S)
            quiet = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_B})
            )
            late_quiet = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_LATE_EDIT})
            )

    # Restart with the gate on: the opening catch-up pass covers it all.
    _write_config(ws, watch_enabled=True)
    async with stdio_client(_server_params(ws)) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=180)
        ) as session:
            await session.initialize()
            caught_up = await _wait_for_text(
                session, NEEDLE_B, deadline_s=SEARCH_DEADLINE_S
            )
            late_caught_up = await _wait_for_text(
                session, NEEDLE_LATE_EDIT, deadline_s=SEARCH_DEADLINE_S
            )
    return {
        "before": before,
        "quiet": quiet,
        "late_quiet": late_quiet,
        "caught_up": caught_up,
        "late_caught_up": late_caught_up,
    }


def test_gate_off_watches_nothing_and_scope_is_fixed_at_startup(
    local_workspace, tmp_path: Path
) -> None:
    ws = local_workspace
    _write_config(ws, watch_enabled=False)
    corpus_a = _corpus(tmp_path, "corpus-a", NEEDLE_A)
    corpus_late = _corpus(tmp_path, "corpus-late", NEEDLE_LATE)
    _create(corpus_a, collection=COLLECTION)

    payload = asyncio.run(_gated_sessions(ws, corpus_a, corpus_late))

    assert "penguin" in _texts(payload["before"]), payload["before"]
    assert "walrus" not in _texts(payload["quiet"]), (
        f"watch_enabled=false must not add a watcher: {payload['quiet']!r}"
    )
    assert "orca" not in _texts(payload["late_quiet"]), (
        "a collection created after startup must not be watched until restart: "
        f"{payload['late_quiet']!r}"
    )
    # The restart's catch-up pass (not a live watcher) makes both fresh.
    assert "walrus" in _texts(payload["caught_up"]), payload["caught_up"]
    assert "orca" in _texts(payload["late_caught_up"]), payload["late_caught_up"]
