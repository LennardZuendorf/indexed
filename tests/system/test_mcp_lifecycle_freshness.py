"""Lifecycle regression: one long-lived MCP process vs. on-disk changes (#112/#125).

Drives the real out-of-process stdio server (an in-process client SEGFAULTS with
llama-index + torch) and asserts what an agent can observe through one process:
an external rebuild is picked up without a restart, and a collection that becomes
unreadable is reported as a failure — never "unknown collection", never silence.

Scope is per request (#345): every call resolves the client's MCP roots to the
``indexed.toml`` committed at the repository root and serves exactly its
selection from the global store. A collection created mid-run therefore becomes
visible only once the definition names it — and, because nothing is cached, on
the very next call after that edit.
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

COLLECTION = "mcp-lifecycle"
NEW_COLLECTION = "mcp-lifecycle-new"
NEEDLE_A = "penguin migration survey along the Antarctic coastline"
NEEDLE_B = "walrus haul-out census across the Bering shelf"
NEEDLE_NEW = "heron rookery census along the tidal marsh"
NEEDLE_RECREATED = "orca pod tracking across the fjord"


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


def _store(home: Path) -> Path:
    """The global collections directory a definition pins (``~/.indexed/data``)."""
    return home / ".indexed" / "data" / "collections"


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
    result = runner.invoke(app, ["--log-level", "ERROR", *args])
    assert result.exit_code == 0, result.stdout + result.stderr


def _create(corpus: Path, *, force: bool = False, collection: str = COLLECTION) -> None:
    args = [
        "--engine",
        "v2",
        "create",
        "files",
        "--collection",
        collection,
        "--path",
        str(corpus),
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
        ["--simple-output", "--log-level", "ERROR", "inspect", collection],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


async def _resource(session, uri: str) -> dict:
    result = await session.read_resource(uri)
    return json.loads(result.contents[0].text)


def _status(payload: dict, name: str) -> dict | None:
    return next((c for c in payload["collections"] if c["name"] == name), None)


def _hits(payload: dict) -> list[dict]:
    """All hits of a payload, flattened across its documents (``indexed.search/1``)."""
    return [hit for doc in payload.get("documents") or [] for hit in doc["hits"]]


def _texts(payload: dict) -> str:
    return " ".join(hit["text"].lower() for hit in _hits(payload))


async def _lifecycle(
    repo: Path,
    store: Path,
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
        cwd=str(repo),
        env={**os.environ, "TQDM_DISABLE": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read,
            write,
            list_roots_callback=_roots_callback(repo),
            read_timeout_seconds=timedelta(seconds=180),
        ) as session:
            await session.initialize()
            await asyncio.to_thread(_create, corpus_a)
            # The definition can name the collection only once the store has it.
            _define(repo, COLLECTION)
            before = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_A})
            )

            # Externally rebuild the SAME collection name while the server lives.
            await asyncio.to_thread(_create, corpus_b, force=True)
            manifest = store / COLLECTION / "manifest.json"
            assert json.loads(manifest.read_text())["version"] == "2"
            after = _extract_payload(
                await session.call_tool("search", {"query": NEEDLE_B})
            )

            # A NEW collection appears on disk while the server lives. Scope is
            # re-resolved per request, so the definition edit alone publishes it.
            await asyncio.to_thread(_create, corpus_new, collection=NEW_COLLECTION)
            _define(repo, COLLECTION, NEW_COLLECTION)
            new_list = await _resource(session, "resource://collections")
            new_status = await _resource(session, "resource://collections/status")
            new_disk = await asyncio.to_thread(_disk, NEW_COLLECTION)
            new_search = _extract_payload(
                await session.call_tool(
                    "search_collection",
                    {"collection": NEW_COLLECTION, "query": NEEDLE_NEW},
                )
            )

            # Removal: while the definition still names it the request fails
            # closed; once the definition is fixed it is outside the scope.
            await asyncio.to_thread(_remove, NEW_COLLECTION)
            gone_failed = _extract_payload(
                await session.call_tool(
                    "search_collection",
                    {"collection": NEW_COLLECTION, "query": NEEDLE_NEW},
                )
            )
            _define(repo, COLLECTION)
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
                _create, corpus_recreated, collection=NEW_COLLECTION
            )
            _define(repo, COLLECTION, NEW_COLLECTION)
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
        "gone_failed": gone_failed,
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
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(isolated_home)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    corpora = (
        _corpus(tmp_path, "corpus-a", NEEDLE_A),
        _corpus(tmp_path, "corpus-b", NEEDLE_B),
        _corpus(tmp_path, "corpus-new", NEEDLE_NEW),
        _corpus(tmp_path, "corpus-recreated", NEEDLE_RECREATED),
    )
    payload = asyncio.run(_lifecycle(repo, store, *corpora))

    # 1. freshness: the same process answers from the rebuilt index.
    assert _hits(payload["before"]), f"initial search empty: {payload!r}"
    assert "penguin" in payload["before"]["documents"][0]["hits"][0]["text"].lower()
    texts = _texts(payload["after"])
    assert _hits(payload["after"]), f"post-rebuild search empty: {payload!r}"
    assert "walrus" in texts, f"same process served a stale index: {payload!r}"
    assert "penguin" not in texts, f"served pre-rebuild content: {payload!r}"

    # 2. a collection published in the definition after startup is visible to
    #    the live process: scope is resolved per request, not at startup.
    assert payload["new_list"]["collections"] == [COLLECTION, NEW_COLLECTION], payload
    new = _status(payload["new_status"], NEW_COLLECTION)
    assert new, payload
    for key in ("number_of_documents", "number_of_chunks"):
        assert new[key] > 0, payload
        assert new[key] == payload["new_disk"][key], payload
    assert "heron" in _texts(payload["new_search"]), payload

    # 3. a selected collection the store removed is answered per source: the
    #    definition still names it, so the request is scoped to it and the store
    #    says it is not there — never a silent empty success (#340).
    failure = payload["gone_failed"]["error"]
    assert NEW_COLLECTION in failure, failure
    assert "documents" not in payload["gone_failed"], payload["gone_failed"]

    #    Once the definition is corrected the same name is outside the scope.
    assert payload["gone_list"]["collections"] == [COLLECTION], payload
    assert _status(payload["gone_status"], NEW_COLLECTION) is None, payload
    assert payload["gone_search"]["type"] == "CollectionOutsideScopeError", payload
    assert "documents" not in payload["gone_search"], payload
    assert NEW_COLLECTION in payload["gone_search"]["error"], payload

    # 4. re-creation serves the new content, not the removed content.
    assert payload["recreated_list"]["collections"] == [
        COLLECTION,
        NEW_COLLECTION,
    ], payload
    recreated = _status(payload["recreated_status"], NEW_COLLECTION)
    assert recreated, payload
    for key in ("number_of_documents", "number_of_chunks"):
        assert recreated[key] == payload["recreated_disk"][key], payload
    assert "orca" in _texts(payload["recreated_search"]), payload
    assert "heron" not in _texts(payload["recreated_search"]), payload
    assert "heron" not in _texts(payload["stale_search"]), payload

    # 5. corruption is a failure, not a miss and not a typo hint. A scoped search
    #    degrades per source (#340): the healthy collection still answers, and the
    #    corrupted one is named — never silently dropped from the scope.
    assert "error" in payload["single"], payload
    assert "not found" not in str(payload["single"]["error"]).lower()
    every = payload["every"]
    assert set(every["collections"]) == {NEW_COLLECTION}, every
    assert [entry["collection"] for entry in every["collection_errors"]] == [
        COLLECTION
    ], every
    corrupt = next(
        source for source in every["sources"] if source["collection"] == COLLECTION
    )
    assert corrupt["status"] in {"unusable", "failed"}, every
    assert COLLECTION in corrupt["error"], every
