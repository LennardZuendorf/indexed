"""System test: the CLI and the MCP server share one root and one view (#112).

Criterion 4 of issue #112: "Verify CLI and MCP use same configured storage root
in global/local modes, including mixed v1/v2 collections".

The in-process case below already covered the *local-mode path-resolution* half:
``resolve_collections_context`` and the MCP lifespan return the same
``collections_path``. It never builds a mixed-engine store, never touches global
mode, and never starts a server.

The parametrised cases below close that gap: ONE live out-of-process stdio
server runs next to the CLI over a store holding one v1-engine and one
v2-engine collection, in global mode and in ``--local`` mode, asserting that

1. both surfaces resolve the SAME storage root — each side's reported
   collection path resolves to the identical absolute directory;
2. both see the SAME collection set with the same per-collection doc/chunk
   counts;
3. each collection's own engine survives on the CLI listing, and the MCP
   per-collection tool still routes the v1 collection through its manifest
   rather than the configured default engine;
4. a search spanning both engines returns both collections' hits with
   per-collection provenance intact, and the two surfaces' envelopes agree.

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


def _create(engine: str, collection: str, corpus: Path, *, local: bool) -> None:
    mode_flag = ["--local"] if local else []
    # ``create`` carries its OWN ``--local`` (it forces the storage mode for the
    # create itself), so it is passed only on the local leg — a stray flag here
    # would silently write a "global" collection into the cwd store.
    _invoke(
        [
            "--engine",
            engine,
            *mode_flag,
            "create",
            "files",
            "--collection",
            collection,
            "--path",
            str(corpus),
            *mode_flag,
            "--no-cache",
        ]
    )


def _cli_list(*, local: bool) -> list[dict]:
    mode_flag = ["--local"] if local else []
    result = runner.invoke(
        app, ["--log-level", "ERROR", *mode_flag, "--simple-output", "inspect"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _cli_search(query: str, *, local: bool) -> dict:
    mode_flag = ["--local"] if local else []
    result = runner.invoke(
        app,
        ["--log-level", "ERROR", *mode_flag, "--simple-output", "search", query],
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


async def _drive_mcp(cwd: Path, query: str) -> dict:
    """Drive ONE live stdio server from ``cwd``: list, status, search, search_collection."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "indexed.mcp.cli", "run", "--no-banner"],
        cwd=str(cwd),
        env={**os.environ, "TQDM_DISABLE": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=180)
        ) as session:
            await session.initialize()
            return {
                "list": await _resource(session, "resource://collections"),
                "status": await _resource(session, "resource://collections/status"),
                "search": _extract_payload(
                    await session.call_tool("search", {"query": query})
                ),
                "search_v1": _extract_payload(
                    await session.call_tool(
                        "search_collection", {"collection": V1, "query": V1_NEEDLE}
                    )
                ),
                "search_v2": _extract_payload(
                    await session.call_tool(
                        "search_collection", {"collection": V2, "query": V2_NEEDLE}
                    )
                ),
            }


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


@pytest.mark.parametrize("mode", ["global", "local"])
def test_cli_and_mcp_agree_over_mixed_v1_v2_store(
    mode: str,
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = mode == "local"
    cli_cwd = tmp_path / "cli-cwd"
    cli_cwd.mkdir()
    # The MCP server runs from a DIFFERENT directory than the CLI in global
    # mode, so an agreeing root cannot be an accident of a shared cwd.
    mcp_cwd = cli_cwd if local else tmp_path / "mcp-cwd"
    mcp_cwd.mkdir(exist_ok=True)

    if local:
        storage_root = get_local_root(cli_cwd)
        ensure_storage_dirs(storage_root, is_local=True)
        (storage_root / "config.toml").touch()
    else:
        storage_root = isolated_home / ".indexed"

    monkeypatch.chdir(cli_cwd)
    reload_config()
    collections_dir = storage_root / "data" / "collections"

    # One v1-engine and one v2-engine collection in the SAME root.
    _create("v1", V1, _corpus(tmp_path, "corpus-v1", V1_NEEDLE), local=local)
    _create("v2", V2, _corpus(tmp_path, "corpus-v2", V2_NEEDLE), local=local)
    assert detect_engine_version(collections_dir / V1) == "1"
    assert detect_engine_version(collections_dir / V2) == "2"

    # --- CLI side ---
    cli_rows = {row["name"]: row for row in _cli_list(local=local)}
    assert set(cli_rows) == {V1, V2}, cli_rows
    assert {name: cli_rows[name]["engine"] for name in (V1, V2)} == {V1: "1", V2: "2"}
    cli_search = _cli_search(NEEDLE, local=local)

    # --- one live out-of-process MCP server, same on-disk store ---
    payload = asyncio.run(_drive_mcp(mcp_cwd, NEEDLE))

    # 1. SAME ROOT: each surface's collection path resolves to the same
    #    absolute directory (and to the root the fixture built).
    assert set(payload["list"]["collections"]) == set(cli_rows)
    mcp_status = {c["name"]: c for c in payload["status"]["collections"]}
    assert set(mcp_status) == set(cli_rows)
    for name in (V1, V2):
        cli_abs = (cli_cwd / cli_rows[name]["path"]).resolve()
        mcp_abs = (mcp_cwd / mcp_status[name]["relative_path"]).resolve()
        assert cli_abs == mcp_abs == (collections_dir / name).resolve(), (
            f"{mode}: {name} resolved to different roots "
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
        f"{mode}: CLI and MCP disagree on search hits "
        f"(cli={_hits(cli_search)}, mcp={mcp_hits})"
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
        assert hits, f"{mode}: {key} returned no hits: {payload[key]}"
        assert {collection for collection, _ in hits} == {name}, payload[key]
        assert "not found" not in str(payload[key]).lower()
