"""System smoke: MCP v2 search driven OUT-OF-PROCESS over real stdio
(core-v2/8, R4 + tech.md "MCP: v2 e2e MUST run out-of-process").

The in-process FastMCP client + llama-index + torch SEGFAULTS (exit 139 —
verified in PR #86 and recorded in tech.md/research.md), so this test spawns the
real ``indexed-mcp`` server as a SEPARATE subprocess over stdio and drives one
v2 search through it with the low-level ``mcp`` stdio client. It is a smoke test
by design: one round trip proving a v2 collection is searchable through the
agent-facing MCP surface end to end.

Storage: the collection lives in an isolated GLOBAL store (``$HOME/.indexed``),
``indexed.toml`` at the repository root selects it, and the client advertises
that repository as its MCP root — so the server resolves the request's scope on
the call itself (#345) rather than from its working directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Iterator

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from indexed.config import reload as reload_config
from tests.conftest import model_available

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "mcp-v2-net"
NEEDLE_QUERY = "penguin migration survey along the Antarctic coastline"


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point global storage (``~/.indexed``) at ``tmp_path/home`` (cf. #112)."""
    # Honour an explicit cache setting; only fall back to the default location.
    real_hf_home = Path(
        os.environ.get("HF_HOME") or Path(os.environ["HOME"]) / ".cache" / "huggingface"
    )
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HF_HOME", str(real_hf_home))
    monkeypatch.setenv(
        "SENTENCE_TRANSFORMERS_HOME",
        os.environ.get("SENTENCE_TRANSFORMERS_HOME") or str(real_hf_home / "hub"),
    )
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TQDM_DISABLE", "1")
    monkeypatch.setattr(Path, "home", lambda: home)
    reload_config()
    yield home
    reload_config()


def _define(repo: Path, *names: str) -> Path:
    """Write the workspace definition selecting ``names`` from the global store."""
    entries = ", ".join(f'"{name}"' for name in names)
    path = repo / "indexed.toml"
    path.write_text(
        f"version = 1\n\n[collections]\nuse = [{entries}]\n", encoding="utf-8"
    )
    return path


def _roots_callback(*repos: Path):
    """Advertise ``repos`` as the client's MCP roots (declares the capability)."""
    from mcp.types import FileUrl, ListRootsResult, Root

    async def callback(_context):
        return ListRootsResult(
            roots=[
                Root(uri=FileUrl(repo.resolve().as_uri()), name=repo.name)
                for repo in repos
            ]
        )

    return callback


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


async def _drive_mcp_search(repo: Path) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "indexed.mcp.cli", "run", "--no-banner"],
        cwd=str(repo),
        env={**os.environ, "TQDM_DISABLE": "1"},
    )
    # Generous read timeout: the FIRST v2 search loads the embedding model in the
    # server subprocess (a few seconds), well within this bound.
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read,
            write,
            list_roots_callback=_roots_callback(repo),
            read_timeout_seconds=timedelta(seconds=120),
        ) as session:
            await session.initialize()
            result = await session.call_tool("search", {"query": NEEDLE_QUERY})
    return _extract_payload(result)


def test_mcp_v2_search_out_of_process(
    tmp_path: Path,
    isolated_home: Path,
    files_corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    # Create the v2 collection in-process (fast); the subprocess only reads it.
    # No ``--local``: with no local ``.indexed`` here, the global store is used.
    created = runner.invoke(
        app,
        [
            "--engine",
            "v2",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--collection",
            COLLECTION,
            "--path",
            str(files_corpus),
            "--no-cache",
        ],
    )
    assert created.exit_code == 0, created.stdout + created.stderr
    collections_dir = isolated_home / ".indexed" / "data" / "collections"
    manifest = json.loads((collections_dir / COLLECTION / "manifest.json").read_text())
    assert manifest["version"] == "2", "collection must be a v2 collection"

    # The definition selects it from the global store; the client's root is the
    # repository that carries the definition.
    _define(repo, COLLECTION)

    payload = asyncio.run(_drive_mcp_search(repo))

    results = payload.get("documents") or []
    assert results, f"MCP v2 search returned no results: {payload!r}"
    top = results[0]
    assert top["id"].endswith("needle.txt"), (
        f"expected needle.txt as top MCP v2 hit, got {top['id']!r}"
    )
    assert top["collection"] == COLLECTION
    assert top["source_type"] == "localFiles"
    assert "penguin" in top["hits"][0]["text"].lower()
