"""Live proof: the MCP server keeps ``localFiles`` collections fresh (#67 slice 2).

Drives the real out-of-process stdio server. With ``[mcp] watch_enabled = true``
a file written into the collection's source tree becomes searchable through the
*same* session — no ``index update``, no restart. With the gate off nothing is
watched, and a collection created while the server runs is only watched after
the next restart (startup determines the scope).

A restart is bounded work too (#358). Every collection that existed at startup
runs its own opening catch-up pass, so a restart owes two things: the *first*
search answers, and every pre-restart edit is searchable inside
``CATCH_UP_BOUND_S``. Both are asserted, and both can be made to fail on demand:
``INDEXED_WATCH_CATCHUP_BOUND_S=0.05`` drops the bound below any real catch-up,
which is how the bound is shown to bite rather than to decorate.
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

_REQUIRE_LIVE_MODEL = os.environ.get("INDEXED_REQUIRE_LIVE_MODEL") == "1"

# Checked at import, not inside the fixture: the session-scoped autouse
# ``isolate_config_paths`` sandboxes ``HOME`` before any fixture runs, so a
# check made later would look in the fake home and never find the real cache.
_MODEL_CACHED = model_available()


@pytest.fixture(scope="module", autouse=True)
def _live_embedding_model() -> None:
    """Require the real model — or say so out loud.

    Locally a missing model skips, because nobody wants a 90 MB download in a
    unit loop. On CI ``INDEXED_REQUIRE_LIVE_MODEL=1`` turns that skip into a
    failure: a system test that quietly does not run looks exactly like one that
    passed, and this file is the only proof of the watcher contract.
    """
    if _MODEL_CACHED:
        return
    reason = "Embedding model not cached (requires all-MiniLM-L6-v2)"
    if _REQUIRE_LIVE_MODEL:
        pytest.fail(f"{reason} — INDEXED_REQUIRE_LIVE_MODEL=1 forbids the skip")
    pytest.skip(reason)


COLLECTION = "mcp-watch"
COLLECTION_LATE = "mcp-watch-late"
NEEDLE_A = "penguin migration survey along the Antarctic coastline"
NEEDLE_B = "walrus haul-out census across the Bering shelf"
NEEDLE_LATE = "heron rookery census along the tidal marsh"
NEEDLE_LATE_EDIT = "orca pod tracking across the fjord"
NEEDLE_RESTART_B = "narwhal migration corridor beneath the pack ice"
NO_WATCH_WINDOW_S = 6.0

#: #358 bounds, both taken from the Linux run recorded on the PR. A restart with
#: two edited v2 collections answered its first search in 2.2 s and had both
#: edits searchable 9.4 s after the process started; a single collection came in
#: at 6.4 s. The bound is that measurement rounded up with room for a cold CI
#: runner, and it still fails the old behaviour — which never finished at all.
IMMEDIATE_SEARCH_BOUND_S = 20.0
CATCH_UP_BOUND_S = 45.0


def _bound(name: str, default: float) -> float:
    """A bound, overridable so the assertion can be watched failing.

    CI never sets these; they exist so ``INDEXED_WATCH_CATCHUP_BOUND_S=0.05``
    turns this file red on a machine where catch-up actually works.
    """
    return float(os.environ.get(f"INDEXED_WATCH_{name}", default))


def _catch_up_bound() -> float:
    return _bound("CATCHUP_BOUND_S", CATCH_UP_BOUND_S)


def _immediate_bound() -> float:
    return _bound("IMMEDIATE_SEARCH_BOUND_S", IMMEDIATE_SEARCH_BOUND_S)


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


async def _wait_for_text(
    session, needle: str, *, origin: float, bound_s: float
) -> tuple[dict, float]:
    """Poll the live session until its results mention ``needle`` — within a bound.

    ``origin`` is the ``time.monotonic()`` the clock is measured from (the
    restart, or the write for a live edit), so the caller gets a duration it can
    assert on instead of "eventually". Missing the bound is a failure, not a
    longer wait: #358 is a catch-up that never finished, and the old 120 s
    deadline could not tell that apart from a slow machine.
    """
    deadline = origin + bound_s
    last: dict = {}
    while time.monotonic() < deadline:
        try:
            last = _extract_payload(
                await session.call_tool("search", {"query": needle})
            )
        except Exception as exc:  # noqa: BLE001 — the index dir swaps mid-update
            last = {"transient_error": str(exc)}
        if needle.split()[0] in _texts(last):
            return last, time.monotonic() - origin
        await asyncio.sleep(0.5)
    raise AssertionError(
        f"{needle!r} was not searchable within {bound_s:g}s; last payload: {last!r}"
    )


async def _immediate_search(
    session, query: str, *, bound_s: float
) -> tuple[dict, float]:
    """The first search after a restart must answer — no retry, no tolerance.

    The failure behind #358 was a search that could not answer at all, because a
    watcher thread had left LlamaIndex half-initialised in the server process.
    Polling past that would hide the ordering bug, so this call is the one place
    in this file that is not allowed to retry.
    """
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(
            session.call_tool("search", {"query": query}), timeout=bound_s
        )
    except TimeoutError as exc:
        raise AssertionError(
            f"the first search after a restart did not answer within {bound_s:.1f}s"
        ) from exc
    return _extract_payload(result), time.monotonic() - started


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
            written_at = time.monotonic()
            (corpus / "delta.txt").write_text(
                "The volcanic sulfur survey found deposits near the caldera rim "
                "and the walrus haul-out census across the Bering shelf.\n"
            )
            after, elapsed = await _wait_for_text(
                session, NEEDLE_B, origin=written_at, bound_s=_catch_up_bound()
            )
    print(f"live edit searchable {elapsed:.1f}s after the write")
    return {"before": before, "after": after, "elapsed_s": elapsed}


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
    restarted_at = time.monotonic()
    async with stdio_client(_server_params(ws)) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=180)
        ) as session:
            await session.initialize()
            caught_up, caught_up_s = await _wait_for_text(
                session, NEEDLE_B, origin=restarted_at, bound_s=_catch_up_bound()
            )
            late_caught_up, late_caught_up_s = await _wait_for_text(
                session,
                NEEDLE_LATE_EDIT,
                origin=restarted_at,
                bound_s=_catch_up_bound(),
            )
    print(
        "gate-off restart: first collection caught up "
        f"{caught_up_s:.1f}s, late collection {late_caught_up_s:.1f}s after restart"
    )
    return {
        "before": before,
        "quiet": quiet,
        "late_quiet": late_quiet,
        "caught_up": caught_up,
        "late_caught_up": late_caught_up,
        "caught_up_s": caught_up_s,
        "late_caught_up_s": late_caught_up_s,
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
    # The restart's catch-up pass (not a live watcher) makes both fresh — and it
    # is held to the same bound as the gate-on restart (#358).
    assert "walrus" in _texts(payload["caught_up"]), payload["caught_up"]
    assert "orca" in _texts(payload["late_caught_up"]), payload["late_caught_up"]


async def _restart_and_measure(ws, edited: list[tuple[str, str, str]]) -> dict:
    """Restart the server and measure the catch-up it owes (#358).

    ``edited`` is ``(collection, original_needle, edit_needle)`` for every
    collection that existed before the restart and whose file changed while the
    server was down. The clock starts before the server process is spawned:
    that is the wait a client actually sees.
    """
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    restarted_at = time.monotonic()
    async with stdio_client(_server_params(ws)) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=180)
        ) as session:
            await session.initialize()
            # Acceptance #358, first half: this must answer, full stop.
            immediate, immediate_s = await _immediate_search(
                session, edited[0][1], bound_s=_immediate_bound()
            )
            print(
                f"restart: first search answered in {immediate_s:.1f}s "
                f"(bound {_immediate_bound():.1f}s)"
            )
            caught_up: dict[str, tuple[dict, float]] = {}
            for collection, _original, edit in edited:
                payload, elapsed = await _wait_for_text(
                    session, edit, origin=restarted_at, bound_s=_catch_up_bound()
                )
                print(
                    f"restart: {collection} edit searchable {elapsed:.1f}s after "
                    f"start (bound {_catch_up_bound():.1f}s)"
                )
                caught_up[collection] = (payload, elapsed)
    return {
        "immediate": immediate,
        "immediate_s": immediate_s,
        "caught_up": caught_up,
    }


RESTART_CORPORA = (
    (COLLECTION, NEEDLE_A, NEEDLE_B),
    (COLLECTION_LATE, NEEDLE_LATE, NEEDLE_RESTART_B),
)


@pytest.mark.parametrize("count", [1, 2], ids=["single-collection", "two-collections"])
def test_restart_serves_immediately_and_catches_up_every_edited_v2_collection(
    local_workspace, tmp_path: Path, count: int
) -> None:
    """#358: a restart over v2 collections answers, then catches every edit up.

    One and two collections are both covered on purpose: the defect needed two
    watchers racing the one-time import, and the single-collection case must
    keep passing so a fix cannot buy multi-collection catch-up by breaking the
    case that always worked.
    """
    ws = local_workspace
    _write_config(ws, watch_enabled=True)
    edited = RESTART_CORPORA[:count]
    for collection, original, _edit in edited:
        corpus = _corpus(tmp_path, collection, original)
        _create(corpus, collection=collection, engine="v2")

    # The edits land while the server is down: this measures the opening
    # catch-up pass, not the live watcher.
    for collection, _original, edit in edited:
        (tmp_path / collection / "delta.txt").write_text(f"# Late edit\n\n{edit}\n")

    measured = asyncio.run(_restart_and_measure(ws, list(edited)))

    assert edited[0][1].split()[0] in _texts(measured["immediate"]), (
        "the first search after a restart must answer with the collection's "
        f"existing content: {measured['immediate']!r}"
    )
    for collection, _original, edit in edited:
        payload, elapsed = measured["caught_up"][collection]
        assert edit.split()[0] in _texts(payload), (
            f"{collection}: the pre-restart edit was never indexed: {payload!r}"
        )
        assert elapsed <= _catch_up_bound(), (
            f"{collection}: edit searchable {elapsed:.1f}s after the restart, past "
            f"the {_catch_up_bound():.1f}s bound (#358 is a catch-up that never "
            "finishes — widening this bound hides it again)"
        )
        assert (ws.collections_dir / collection).is_dir()


def test_accompanying_guards_are_collected(request) -> None:
    """The guards #358 must not regress are present — never silently absent.

    A module-level skip in this file would hide every test in it, so the check
    that matters here is that the nodes exist at all; ``-rs`` reports their
    outcome and ``INDEXED_REQUIRE_LIVE_MODEL=1`` turns a skip into a failure in
    CI, which together close the "quietly did not run" hole.
    """
    collected = {item.originalname for item in request.session.items}
    required = {
        "test_gate_off_watches_nothing_and_scope_is_fixed_at_startup",
        "test_live_edit_becomes_searchable_without_a_restart",
        "test_restart_serves_immediately_and_catches_up_every_edited_v2_collection",
    }
    missing = sorted(required - collected)
    assert not missing, f"guards silently absent from this module: {missing}"
