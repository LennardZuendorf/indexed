"""Per-request MCP scope, end to end (#345).

One long-lived server, two clients in two repositories, one shared global store.
This is the acceptance test for the milestone's foundation: a client cannot see
another project's collections, and a client that presents no scope (or an
ambiguous one) is told so instead of searching the whole store.

Out-of-process on purpose: an in-process FastMCP client next to llama-index and
torch segfaults, the reason recorded in ``docs/spec/lessons.md``. One HTTP server
is shared by every client below, which is the deployment this feature exists for.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Iterator

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from indexed.cli.composition import resolve_collections_context
from indexed.config import reload as reload_config
from indexed.lsp.backend import KnowledgeBackend
from tests.conftest import model_available

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

runner = CliRunner()

ALPHA = "alpha-docs"
BETA = "beta-docs"
ALPHA_NEEDLE = "penguin migration survey along the Antarctic coastline"
BETA_NEEDLE = "heron rookery census along the tidal marsh"


# --- harness -----------------------------------------------------------------


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


def _corpus(root: Path, name: str, needle: str) -> Path:
    corpus = root / name
    corpus.mkdir(parents=True)
    (corpus / "needle.txt").write_text(f"# Survey\n\n{needle}\n")
    (corpus / "notes.txt").write_text("# Notes\n\nField logistics and staffing.\n")
    return corpus


def _create(collection: str, corpus: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--log-level",
            "ERROR",
            "--engine",
            "1",
            "create",
            "files",
            "--collection",
            collection,
            "--path",
            str(corpus),
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr


def _define(repo: Path, *names: str) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(f'"{name}"' for name in names)
    path = repo / "indexed.toml"
    path.write_text(
        f"version = 1\n\n[collections]\nuse = [{entries}]\n", encoding="utf-8"
    )
    return path


def _free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(
    proc: subprocess.Popen[str], port: int, timeout: float = 120.0
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(
                f"server exited before listening (rc={proc.returncode})"
            )
        with closing(socket.socket()) as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise AssertionError(f"server did not listen on {port} within {timeout}s")


@pytest.fixture
def server(tmp_path: Path) -> Iterator[str]:
    """One long-lived HTTP server, shared by every client in the test."""
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "indexed.mcp.cli",
            "run",
            "--transport",
            "http",
            "--port",
            str(port),
            "--no-banner",
            "--log-level",
            "ERROR",
        ],
        cwd=str(tmp_path),
        env={**os.environ, "TQDM_DISABLE": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_port(proc, port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()
            proc.wait(timeout=10)


def _payload(result: Any) -> dict:
    """Pull a tool's dict result out of an MCP ``CallToolResult``."""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no parseable payload in MCP result: {result!r}")


async def _read(client: Any, uri: str) -> dict:
    contents = await client.read_resource(uri)
    return json.loads(contents[0].text)


def _roots(*repos: Path) -> list[Any]:
    from mcp.types import FileUrl, Root

    return [
        Root(uri=FileUrl(repo.resolve().as_uri()), name=repo.name) for repo in repos
    ]


def _doc_collections(payload: dict) -> set[str]:
    return {document["collection"] for document in payload["documents"]}


def _doc_ids(payload: dict) -> set[str]:
    return {document["id"] for document in payload["documents"]}


# --- the acceptance test -----------------------------------------------------


def test_two_clients_see_their_own_selection(
    tmp_path: Path, isolated_home: Path, server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastmcp import Client

    alpha_corpus = _corpus(tmp_path / "corpora", "alpha", ALPHA_NEEDLE)
    beta_corpus = _corpus(tmp_path / "corpora", "beta", BETA_NEEDLE)
    _create(ALPHA, alpha_corpus)
    _create(BETA, beta_corpus)
    alpha = tmp_path / "repos" / "alpha"
    beta = tmp_path / "repos" / "beta"
    _define(alpha, ALPHA)
    _define(beta, BETA)

    async def drive() -> dict:
        async with (
            Client(server, roots=_roots(alpha)) as a,
            Client(server, roots=_roots(beta)) as b,
        ):
            # Concurrently, against the one server.
            a_search, b_search = await asyncio.gather(
                a.call_tool("search", {"query": ALPHA_NEEDLE}),
                b.call_tool("search", {"query": BETA_NEEDLE}),
            )
            a_names, b_names = await asyncio.gather(
                _read(a, "resource://collections"),
                _read(b, "resource://collections"),
            )
            a_status, b_status = await asyncio.gather(
                _read(a, "resource://collections/status"),
                _read(b, "resource://collections/status"),
            )
            return {
                "a": _payload(a_search),
                "b": _payload(b_search),
                "a_names": a_names,
                "b_names": b_names,
                "a_status": a_status,
                "b_status": b_status,
            }

    out = asyncio.run(drive())

    # 1. Search is isolated, in both directions, on the same store.
    assert out["a"]["documents"], out["a"]
    assert _doc_collections(out["a"]) == {ALPHA}
    assert out["b"]["documents"], out["b"]
    assert _doc_collections(out["b"]) == {BETA}

    # 2. Status agrees with search for the same client.
    assert out["a_names"]["collections"] == [ALPHA]
    assert out["b_names"]["collections"] == [BETA]
    assert [source["collection"] for source in out["a_names"]["sources"]] == [ALPHA]
    assert [source["collection"] for source in out["b_names"]["sources"]] == [BETA]
    assert [entry["name"] for entry in out["a_status"]["collections"]] == [ALPHA]
    assert [entry["name"] for entry in out["b_status"]["collections"]] == [BETA]
    assert set(out["a"]["collections"]) == {ALPHA}
    assert set(out["b"]["collections"]) == {BETA}

    # 3. CLI parity: the same repository resolves the same selection.
    monkeypatch.chdir(alpha)
    search = runner.invoke(
        app,
        ["--log-level", "ERROR", "--simple-output", "search", ALPHA_NEEDLE],
        catch_exceptions=False,
    )
    cli_payload = json.loads(search.stdout)
    assert set(cli_payload["collections"]) == {ALPHA}
    assert _doc_collections(cli_payload) == {ALPHA}
    assert _doc_ids(cli_payload) == _doc_ids(out["a"])

    # 4. LSP parity: the backend the language server wires gets the same names.
    cli_ctx = resolve_collections_context(workspace=alpha)
    assert cli_ctx.selection is not None
    backend = KnowledgeBackend(
        str(cli_ctx.collections_path),
        selected_names=cli_ctx.selection.names,
    )
    assert [status.name for status in backend.statuses()] == [ALPHA]


def test_a_client_without_scope_is_told_and_sees_nothing(
    tmp_path: Path, isolated_home: Path, server: str
) -> None:
    from fastmcp import Client

    _create(ALPHA, _corpus(tmp_path / "corpora", "alpha", ALPHA_NEEDLE))
    alpha = tmp_path / "repos" / "alpha"
    _define(alpha, ALPHA)

    async def drive() -> tuple[dict, dict]:
        async with Client(server) as scoped_nothing:
            search = await scoped_nothing.call_tool("search", {"query": ALPHA_NEEDLE})
            listing = await scoped_nothing.read_resource("resource://collections")
        return _payload(search), json.loads(listing[0].text)

    search, listing = asyncio.run(drive())

    assert search["type"] == "NoRequestScopeError"
    assert "documents" not in search
    assert listing["type"] == "NoRequestScopeError"
    assert "collections" not in listing


def test_a_client_presenting_two_definitions_is_told_it_is_ambiguous(
    tmp_path: Path, isolated_home: Path, server: str
) -> None:
    from fastmcp import Client

    _create(ALPHA, _corpus(tmp_path / "corpora", "alpha", ALPHA_NEEDLE))
    _create(BETA, _corpus(tmp_path / "corpora", "beta", BETA_NEEDLE))
    alpha = tmp_path / "repos" / "alpha"
    beta = tmp_path / "repos" / "beta"
    _define(alpha, ALPHA)
    _define(beta, BETA)

    async def drive() -> dict:
        async with Client(server, roots=_roots(alpha, beta)) as both:
            result = await both.call_tool("search", {"query": ALPHA_NEEDLE})
        return _payload(result)

    payload = asyncio.run(drive())

    assert payload["type"] == "AmbiguousRequestScopeError"
    assert "documents" not in payload
    assert str(alpha / "indexed.toml") in payload["error"]
    assert str(beta / "indexed.toml") in payload["error"]
