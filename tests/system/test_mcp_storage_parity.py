"""System test: the CLI and the MCP server agree over one root and one view (#112).

Criterion 4 of issue #112: "Verify CLI and MCP use same configured storage root
in global/local modes, including mixed v1/v2 collections".

The MCP server no longer takes its storage root from its own working directory
(#345): every request resolves its scope from the client's MCP roots — the
nearest committed ``indexed.toml`` at or above one of them — and serves that
definition's selection from the GLOBAL store. The cases below therefore run ONE
live out-of-process stdio server next to the CLI over a global store holding one
v1-engine and one v2-engine collection, with the client advertising a repository
whose ``indexed.toml`` selects both, asserting that

1. both surfaces resolve the SAME storage root — each side's reported
   collection path resolves to the identical absolute directory, even though the
   server runs from a directory unrelated to the repository;
2. both see the SAME collection set with the same per-collection doc/chunk
   counts;
3. each collection's own engine survives on the CLI listing, and the MCP
   per-collection tool still routes the v1 collection through its manifest
   rather than the configured default engine;
4. a search spanning both engines returns both collections' hits with
   per-collection provenance intact, and the two surfaces' envelopes agree.

A workspace that holds only a local ``./.indexed`` store and no definition is
now out of scope by design (the #345 ruling), and is asserted as such: the
server says ``NoRequestScopeError`` instead of reading the store under its cwd.

Both surfaces render search through
``indexed.mcp.formatting.build_search_payload`` (the CLI's ``--json`` /
``--simple-output`` path imports it directly), so their envelopes are directly
comparable — the parity claim is about one shared builder fed by two
independently resolved roots, not two unrelated renderers.

Out-of-process is mandatory, not stylistic: an in-process FastMCP client plus
llama-index + torch SEGFAULTS (recorded in tech.md/research.md, PR #86).
"""

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Iterator

import pytest
from typer.testing import CliRunner

from indexed.config import ensure_storage_dirs, get_local_root, reload as reload_config
from indexed.cli.composition import resolve_collections_context
from indexed.cli.app import app
from indexed.core.versioning import detect_engine_version
from tests.conftest import model_available

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

V1 = "parity-mixed-v1"
V2 = "parity-mixed-v2"
LOCAL_ONLY = "parity-local-only"
NEEDLE = "penguin migration survey along the Antarctic coastline"
V1_NEEDLE = "walrus haul-out census across the Bering shelf"
V2_NEEDLE = "heron rookery census along the tidal marsh"


def test_cli_local_and_mcp_lifespan_share_collections_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)
    expected = local_root / "data" / "collections"

    cli_ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)
    assert cli_ctx.collections_path == expected

    async def run_lifespan():
        from indexed.mcp.server import lifespan, mcp

        async with lifespan(mcp) as state:
            return state["cli_context"].collections_path

    mcp_path = asyncio.run(run_lifespan())

    assert mcp_path == expected
    assert cli_ctx.collections_path == mcp_path


# --- harness -----------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point global storage (``~/.indexed``) at ``tmp_path/home`` for one test.

    Same reasoning as ``test_connectors_e2e_cli.isolated_home``: ``get_global_root``
    calls ``Path.home()``, so the session-scoped sandbox patch in
    ``tests/conftest.py`` is re-patched here for true per-test isolation (every
    test in the session shares that one sandbox otherwise). Faking HOME hides
    the HOME-relative HuggingFace cache, so ``HF_HOME`` (which
    ``model_manager._get_hf_cache_dir`` appends ``/hub`` to) and
    ``SENTENCE_TRANSFORMERS_HOME`` (which ``SentenceTransformer`` takes as the
    ``hub`` dir itself) are pointed at the real cache read from the real
    ``HOME`` env var — never ``Path.home()``, already patched by the session
    fixture. ``HF_HUB_OFFLINE`` keeps a cache miss from becoming a network call.
    """
    real_hf_home = Path(os.environ["HOME"]) / ".cache" / "huggingface"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HF_HOME", str(real_hf_home))
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(real_hf_home / "hub"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TQDM_DISABLE", "1")
    monkeypatch.setattr(Path, "home", lambda: home)
    reload_config()
    yield home
    reload_config()


def _corpus(root: Path, name: str, needle: str) -> Path:
    corpus = root / name
    corpus.mkdir()
    (corpus / "needle.txt").write_text(f"# Survey\n\n{needle}\n")
    (corpus / "notes.txt").write_text("# Notes\n\nField logistics and staffing.\n")
    return corpus


def _invoke(args: list[str]) -> None:
    result = runner.invoke(app, ["--log-level", "ERROR", *args])
    assert result.exit_code == 0, result.stdout + result.stderr


def _create(engine: str, collection: str, corpus: Path) -> None:
    # Run from a directory without a definition: a definition may only select
    # collections that already exist in the store, and ``create`` never edits it.
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
            "--no-cache",
        ]
    )


def _define(repo: Path, *names: str) -> Path:
    """Commit the repository's ``indexed.toml`` selecting ``names``, in order."""
    repo.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(f'"{name}"' for name in names)
    path = repo / "indexed.toml"
    path.write_text(
        f"version = 1\n\n[collections]\nuse = [{entries}]\n", encoding="utf-8"
    )
    return path


def _cli_list() -> list[dict]:
    result = runner.invoke(app, ["--log-level", "ERROR", "--simple-output", "inspect"])
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _cli_search(query: str) -> dict:
    result = runner.invoke(
        app,
        ["--log-level", "ERROR", "--simple-output", "search", query],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _extract_payload(result) -> dict:
    """Pull a tool's dict result out of an MCP ``CallToolResult``."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no parseable payload in MCP result: {result!r}")


async def _resource(session, uri: str) -> dict:
    result = await session.read_resource(uri)
    return json.loads(result.contents[0].text)


def _roots_callback(*repos: Path):
    """A client that advertises ``repos`` as its MCP roots (declares the capability)."""
    from mcp.types import FileUrl, ListRootsResult, Root

    async def callback(_context):
        return ListRootsResult(
            roots=[
                Root(uri=FileUrl(repo.resolve().as_uri()), name=repo.name)
                for repo in repos
            ]
        )

    return callback


async def _drive_mcp(
    server_cwd: Path,
    roots: Path,
    query: str,
    *,
    per_collection: bool = True,
) -> dict:
    """Drive ONE live stdio server from ``server_cwd`` as the client at ``roots``.

    ``server_cwd`` is deliberately unrelated to ``roots``: the request's scope
    comes from the roots the client advertises, never from where the server
    happens to run.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "indexed.mcp.cli", "run", "--no-banner"],
        cwd=str(server_cwd),
        env={**os.environ, "TQDM_DISABLE": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read,
            write,
            list_roots_callback=_roots_callback(roots),
            read_timeout_seconds=timedelta(seconds=180),
        ) as session:
            await session.initialize()
            payloads = {
                "list": await _resource(session, "resource://collections"),
                "status": await _resource(session, "resource://collections/status"),
                "search": _extract_payload(
                    await session.call_tool("search", {"query": query})
                ),
            }
            if per_collection:
                payloads["search_v1"] = _extract_payload(
                    await session.call_tool(
                        "search_collection", {"collection": V1, "query": V1_NEEDLE}
                    )
                )
                payloads["search_v2"] = _extract_payload(
                    await session.call_tool(
                        "search_collection", {"collection": V2, "query": V2_NEEDLE}
                    )
                )
            return payloads


def _hits(envelope: dict) -> set[tuple[str, str]]:
    """(collection, document basename) pairs — one per document, not per chunk.

    The payload groups a document's matched chunks under it
    (``indexed.search/1``), so the per-surface comparison is over documents.
    """
    return {
        (doc["collection"], Path(doc["id"]).name)
        for doc in envelope.get("documents") or []
    }


# --- the criterion-4 cases ---------------------------------------------------


def test_cli_and_mcp_agree_over_mixed_v1_v2_store(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_cwd = tmp_path / "cli-cwd"
    cli_cwd.mkdir()
    # The MCP server runs from a DIFFERENT directory than the repository whose
    # definition scopes it, so an agreeing root cannot be an accident of a
    # shared cwd.
    mcp_cwd = tmp_path / "mcp-cwd"
    mcp_cwd.mkdir()

    storage_root = isolated_home / ".indexed"

    monkeypatch.chdir(cli_cwd)
    reload_config()
    collections_dir = storage_root / "data" / "collections"

    # One v1-engine and one v2-engine collection in the SAME (global) root.
    _create("v1", V1, _corpus(tmp_path, "corpus-v1", V1_NEEDLE))
    _create("v2", V2, _corpus(tmp_path, "corpus-v2", V2_NEEDLE))
    assert detect_engine_version(collections_dir / V1) == "1"
    assert detect_engine_version(collections_dir / V2) == "2"

    # The client's repository: the one definition both surfaces resolve.
    repo = tmp_path / "repo"
    _define(repo, V1, V2)

    # --- CLI side, run from the repository (definition first, #344) ---
    monkeypatch.chdir(repo)
    reload_config()
    cli_rows = {row["name"]: row for row in _cli_list()}
    assert set(cli_rows) == {V1, V2}, cli_rows
    assert {name: cli_rows[name]["engine"] for name in (V1, V2)} == {V1: "1", V2: "2"}
    cli_search = _cli_search(NEEDLE)

    # --- one live out-of-process MCP server, same on-disk store ---
    payload = asyncio.run(_drive_mcp(mcp_cwd, repo, NEEDLE))

    # 1. SAME ROOT: each surface's collection path resolves to the same
    #    absolute directory (and to the root the fixture built).
    assert set(payload["list"]["collections"]) == set(cli_rows)
    mcp_status = {c["name"]: c for c in payload["status"]["collections"]}
    assert set(mcp_status) == set(cli_rows)
    for name in (V1, V2):
        cli_abs = (repo / cli_rows[name]["path"]).resolve()
        mcp_abs = (mcp_cwd / mcp_status[name]["relative_path"]).resolve()
        assert cli_abs == mcp_abs == (collections_dir / name).resolve(), (
            f"{name} resolved to different roots "
            f"(cli={cli_abs}, mcp={mcp_abs}, expected={collections_dir / name})"
        )
        assert (
            mcp_status[name]["number_of_documents"]
            == (cli_rows[name]["number_of_documents"])
        )
        assert (
            mcp_status[name]["number_of_chunks"] == cli_rows[name]["number_of_chunks"]
        )

    # 2. Same search universe: the merged envelope carries BOTH engines' hits,
    #    with provenance, and the two surfaces agree hit for hit.
    mcp_hits = _hits(payload["search"])
    assert {collection for collection, _ in mcp_hits} == {V1, V2}, payload["search"]
    assert mcp_hits == _hits(cli_search), (
        f"CLI and MCP disagree on search hits (cli={_hits(cli_search)}, mcp={mcp_hits})"
    )
    for envelope in (payload["search"], cli_search):
        assert not envelope["collection_errors"]
        assert envelope["schema"] == "indexed.search/1"
        assert (
            envelope["counts"]["hits"]
            == sum(len(doc["hits"]) for doc in envelope["documents"])
            > 0
        )
    assert payload["search"]["counts"]["hits"] == cli_search["counts"]["hits"]
    # Mixed set → the cross-engine relevance path ran, tagging each hit with the
    # REAL score kind (v1 has no scoreKind, so it reports l2_squared).
    kinds = {
        (doc["collection"], doc["score_kind"]) for doc in payload["search"]["documents"]
    }
    assert kinds == {(V1, "l2_squared"), (V2, "cosine")}

    # 3. The MCP per-collection tool routes by manifest, so the v1 collection is
    #    searchable through the server even with the default engine at "1"/"2".
    for key, name in (("search_v1", V1), ("search_v2", V2)):
        hits = _hits(payload[key])
        assert hits, f"{key} returned no hits: {payload[key]}"
        assert {collection for collection, _ in hits} == {name}, payload[key]
        assert "not found" not in str(payload[key]).lower()


def test_local_only_workspace_without_a_definition_is_out_of_scope(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local store with no ``indexed.toml`` is no longer a scope (#345).

    The collection really exists — it is created with ``--local`` in the
    workspace the client presents as its root — but a definition is what pins a
    scope, so the server must refuse rather than fall back to the server's cwd.
    """
    del isolated_home
    workspace = tmp_path / "local-only"
    workspace.mkdir()

    monkeypatch.chdir(workspace)
    reload_config()
    local_root = get_local_root(workspace)
    ensure_storage_dirs(local_root, is_local=True)

    result = runner.invoke(
        app,
        [
            "--log-level",
            "ERROR",
            "--local",
            "--engine",
            "1",
            "create",
            "files",
            "--collection",
            LOCAL_ONLY,
            "--path",
            str(_corpus(tmp_path, "corpus-local", NEEDLE)),
            "--local",
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    local_collections = local_root / "data" / "collections"
    assert (local_collections / LOCAL_ONLY / "manifest.json").is_file()
    assert not (workspace / "indexed.toml").exists()

    # The server even runs FROM the workspace: its cwd is not scope any more.
    payload = asyncio.run(
        _drive_mcp(workspace, workspace, NEEDLE, per_collection=False)
    )

    assert payload["search"]["type"] == "NoRequestScopeError", payload["search"]
    assert "documents" not in payload["search"]
    assert payload["list"]["type"] == "NoRequestScopeError", payload["list"]
    assert "collections" not in payload["list"]
