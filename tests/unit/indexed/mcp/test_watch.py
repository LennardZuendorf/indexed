"""Unit tests for the opt-in MCP collection watcher (issue #67 slice 2).

The gate is the contract: with ``[mcp] watch_enabled`` unset the server must
import no watcher module, start no thread and plan nothing. Everything else
here pins the startup-determined scope and the reused data-loss gate.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from indexed.core.v1.config_models import MCPConfig
from indexed.mcp.watch import WatcherHandle, start_watchers_if_enabled

WATCH_SERVICE_MODULE = "indexed.cli.knowledge.commands.watch_service"


def _forget_watch_service() -> None:
    sys.modules.pop(WATCH_SERVICE_MODULE, None)


def _manifest(collections_dir: Path, name: str, base_path: Path) -> None:
    coll = collections_dir / name
    coll.mkdir(parents=True)
    (coll / "manifest.json").write_text(
        json.dumps({"reader": {"type": "localFiles", "basePath": str(base_path)}})
    )


def test_gate_off_starts_nothing_and_imports_no_watcher(tmp_path: Path) -> None:
    """``watch_enabled=False`` is the default: no module, no thread, no task."""
    _forget_watch_service()
    threads_before = threading.active_count()

    handle = asyncio.run(
        start_watchers_if_enabled(
            MCPConfig(),
            collections_path=tmp_path,
            config_service=None,
            manifest_factory=None,
        )
    )

    assert handle is None
    assert WATCH_SERVICE_MODULE not in sys.modules
    assert threading.active_count() == threads_before


def test_targets_cover_local_files_only_and_skip_unreadable_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-local sources and missing source paths are skipped, never updated."""
    import indexed.mcp.watch as watch_module

    good_src = tmp_path / "corpus"
    good_src.mkdir()
    (good_src / "a.txt").write_text("hello\n")
    collections = tmp_path / "collections"
    collections.mkdir()
    _manifest(collections, "local-ok", good_src)
    _manifest(collections, "local-vanished", tmp_path / "gone")

    statuses = [
        SimpleNamespace(name="local-ok", source_type="localFiles", indexers=["v2"]),
        SimpleNamespace(name="jira-issues", source_type="jira", indexers=["v2"]),
        SimpleNamespace(
            name="local-vanished", source_type="localFiles", indexers=["v2"]
        ),
        SimpleNamespace(name="no-indexer", source_type="localFiles", indexers=[]),
    ]
    monkeypatch.setattr("indexed.core.engine.status", lambda **_: statuses)

    planned = watch_module._plan_targets(collections, None)

    assert [target.collection for target, _ in planned] == ["local-ok"]
    assert planned[0][1].indexer == "v2"
    assert planned[0][0].scan() is not None


def test_startup_scope_is_fixed_and_stop_joins_the_threads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One task per target, planned once; a later collection is not added."""
    import indexed.mcp.watch as watch_module

    calls: list[str] = []
    target = SimpleNamespace(collection="local-ok", scan=lambda: None)

    def fake_plan(collections_path, config_service):
        calls.append("plan")
        return [(target, SimpleNamespace(name="local-ok"))]

    def fake_watch_one(target, source_config, *, stop_event, **kwargs):
        stop_event.wait(5)

    monkeypatch.setattr(watch_module, "_plan_targets", fake_plan)
    monkeypatch.setattr(watch_module, "_watch_one", fake_watch_one)

    async def scenario() -> None:
        handle = await watch_module.start_watchers_if_enabled(
            MCPConfig(watch_enabled=True),
            collections_path=tmp_path,
            config_service=None,
            manifest_factory=None,
        )
        assert isinstance(handle, WatcherHandle)
        assert len(handle.tasks) == 1
        # A collection created after startup changes nothing: the plan ran once.
        assert calls == ["plan"]
        await handle.stop()
        assert handle.stop_event.is_set()
        assert all(task.done() for task in handle.tasks)

    asyncio.run(scenario())


def test_opening_catch_up_passes_never_overlap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#358: one collection owns the process's first heavy import.

    Every collection that existed at startup catches up immediately, so two
    collections used to enter LlamaIndex's lazy import (and the embedder load)
    at the same instant; the thread that lost got a half-initialised module,
    which stays in ``sys.modules`` and fails every later pass of that process —
    the macOS system test read that as "catch-up never finished". The barrier
    only releases when *both* opening passes are inside the update, so it times
    out on a serialised fleet: the test is deterministic in both directions
    instead of racing a sleep.
    """
    import indexed.core.engine as engine_module
    import indexed.mcp.watch as watch_module

    together = threading.Barrier(2)
    overlapped = threading.Event()
    passes: list[str] = []

    def fake_update(configs, **_kwargs):
        passes.append(configs[0].name)
        try:
            together.wait(timeout=0.5)  # both passes inside ⇒ they overlapped
            overlapped.set()
        except threading.BrokenBarrierError:  # alone ⇒ serialised, as required
            pass

    def fake_loop(*, apply_update, stop, **_kwargs):
        apply_update()
        stop.wait(5)
        return 0

    targets = [
        (
            SimpleNamespace(collection=f"local-{i}", scan=lambda: None),
            SimpleNamespace(name=f"local-{i}"),
        )
        for i in (1, 2)
    ]
    monkeypatch.setattr(watch_module, "_plan_targets", lambda *_: targets)
    monkeypatch.setattr(engine_module, "update", fake_update)
    monkeypatch.setattr(
        "indexed.cli.knowledge.commands.watch_service.run_watch_loop", fake_loop
    )

    async def scenario() -> None:
        handle = await watch_module.start_watchers_if_enabled(
            MCPConfig(watch_enabled=True),
            collections_path=tmp_path,
            config_service=SimpleNamespace(clear_overlay=lambda: None),
            manifest_factory=None,
        )
        assert isinstance(handle, WatcherHandle)
        await handle.stop()

    started = time.monotonic()
    asyncio.run(scenario())

    assert sorted(passes) == ["local-1", "local-2"], (
        f"both collections must still catch up on startup: {passes!r}"
    )
    assert not overlapped.is_set(), (
        "two opening catch-up passes ran at the same time — the first heavy "
        "import has no single owner (issue #358)"
    )
    # Serialising the opening pass must not serialise the fleet: the wait is
    # one barrier timeout, not one update per collection.
    assert time.monotonic() - started < 3.0


def test_a_broken_collection_does_not_gate_the_fleet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#358: the gate guards the first import, not one collection's failure.

    A collection whose update raises must not keep the gate (and therefore the
    other collections' passes) for its own retries: the first attempt sets the
    warm flag even when it fails.
    """
    import indexed.core.engine as engine_module
    import indexed.mcp.watch as watch_module

    passes: list[str] = []
    both_ran = threading.Event()

    def fake_update(configs, **_kwargs):
        passes.append(configs[0].name)
        if len(passes) == 2:
            both_ran.set()
        if configs[0].name == "broken":
            raise RuntimeError("collection is unreadable")

    def fake_loop(*, apply_update, stop, **_kwargs):
        try:
            apply_update()
        except RuntimeError:
            pass
        stop.wait(5)
        return 0

    targets = [
        (
            SimpleNamespace(collection=name, scan=lambda: None),
            SimpleNamespace(name=name),
        )
        for name in ("broken", "healthy")
    ]
    monkeypatch.setattr(watch_module, "_plan_targets", lambda *_: targets)
    monkeypatch.setattr(engine_module, "update", fake_update)
    monkeypatch.setattr(
        "indexed.cli.knowledge.commands.watch_service.run_watch_loop", fake_loop
    )

    async def scenario() -> bool:
        handle = await watch_module.start_watchers_if_enabled(
            MCPConfig(watch_enabled=True),
            collections_path=tmp_path,
            config_service=SimpleNamespace(clear_overlay=lambda: None),
            manifest_factory=None,
        )
        assert isinstance(handle, WatcherHandle)
        await asyncio.to_thread(both_ran.wait, 5.0)
        warm = handle.stack_warm.is_set()
        await handle.stop()
        return warm

    assert asyncio.run(scenario()) is True, (
        "a failed opening pass must still mark the stack warm, or every later "
        "pass of every collection queues behind this collection's retries"
    )
    assert sorted(passes) == ["broken", "healthy"], passes


def test_missing_source_directory_is_never_a_signature(tmp_path: Path) -> None:
    """The reused data-loss gate: no directory ⇒ ``None`` ⇒ no update."""
    from indexed.cli.knowledge.commands import watch_service

    src = tmp_path / "corpus"
    src.mkdir()
    collections = tmp_path / "collections"
    collections.mkdir()
    _manifest(collections, "local-ok", src)

    target = watch_service.resolve_watch_target("local-ok", collections)
    assert target is not None and target.scan() is not None

    src.rmdir()
    assert target.scan() is None


def test_lifespan_with_gate_off_never_imports_the_watcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifespan's off-path adds no import and no watcher start."""
    import indexed.mcp.server as server_module

    prewarmed: list[str] = []
    monkeypatch.setattr(
        "indexed.parsing._model_window.prewarm_tokenizer",
        lambda: prewarmed.append("prewarm") or True,
        raising=False,
    )
    _forget_watch_service()
    cli_context = MagicMock(collections_path=Path("/nonexistent/collections"))
    monkeypatch.setattr(server_module, "get_config", lambda: MagicMock())
    monkeypatch.setattr(server_module, "register_app_config", lambda _cs: None)
    monkeypatch.setattr(server_module, "resolve_cli_context", lambda _ctx: cli_context)
    monkeypatch.setattr(
        server_module,
        "_get_config",
        lambda model_cls: MCPConfig() if model_cls is MCPConfig else MagicMock(),
    )
    monkeypatch.setattr(server_module, "resolve_engine_selector", lambda *_: "1")

    async def scenario() -> None:
        async with server_module.lifespan(MagicMock()) as state:
            assert state["mcp_config"].watch_enabled is False

    asyncio.run(scenario())
    assert WATCH_SERVICE_MODULE not in sys.modules
    # No watcher ⇒ no worker thread to race ⇒ no eager tokenizer load.
    assert prewarmed == []


def test_lifespan_warms_the_tokenizer_before_starting_watchers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#335: the first ``transformers`` import happens before any watcher thread."""
    import indexed.mcp.server as server_module
    import indexed.mcp.watch as watch_module
    import indexed.parsing._model_window as model_window

    events: list[str] = []
    stop = AsyncMock()

    def fake_prewarm() -> bool:
        events.append("prewarm")
        return True

    async def fake_start(*_args: object, **_kwargs: object) -> SimpleNamespace:
        events.append("start")
        return SimpleNamespace(stop=stop)

    monkeypatch.setattr(model_window, "prewarm_tokenizer", fake_prewarm)
    monkeypatch.setattr(watch_module, "start_watchers_if_enabled", fake_start)
    cli_context = MagicMock(collections_path=Path("/tmp/collections"))
    monkeypatch.setattr(server_module, "get_config", lambda: MagicMock())
    monkeypatch.setattr(server_module, "register_app_config", lambda _cs: None)
    monkeypatch.setattr(server_module, "resolve_cli_context", lambda _ctx: cli_context)
    monkeypatch.setattr(
        server_module,
        "_get_config",
        lambda model_cls: (
            MCPConfig(watch_enabled=True) if model_cls is MCPConfig else MagicMock()
        ),
    )
    monkeypatch.setattr(server_module, "resolve_engine_selector", lambda *_: "1")

    async def scenario() -> None:
        async with server_module.lifespan(MagicMock()):
            # A search is served only after the lifespan yields; the ordering
            # assertion is that the warm-up already ran by then.
            events.append("serving")

    asyncio.run(scenario())

    assert events == ["prewarm", "start", "serving"]
    stop.assert_awaited_once()


def test_lifespan_starts_and_stops_watchers_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The enabled path starts the supervisor and always stops it on exit."""
    import indexed.mcp.server as server_module
    import indexed.mcp.watch as watch_module

    # The real warm-up would load `transformers`; only the wiring is under test.
    monkeypatch.setattr(
        "indexed.parsing._model_window.prewarm_tokenizer",
        lambda: True,
        raising=False,
    )
    cli_context = MagicMock(collections_path=Path("/tmp/collections"))
    stop = AsyncMock()
    handle = SimpleNamespace(stop=stop)
    start = AsyncMock(return_value=handle)
    monkeypatch.setattr(watch_module, "start_watchers_if_enabled", start)
    monkeypatch.setattr(server_module, "get_config", lambda: MagicMock())
    monkeypatch.setattr(server_module, "register_app_config", lambda _cs: None)
    monkeypatch.setattr(server_module, "resolve_cli_context", lambda _ctx: cli_context)
    monkeypatch.setattr(
        server_module,
        "_get_config",
        lambda model_cls: (
            MCPConfig(watch_enabled=True) if model_cls is MCPConfig else MagicMock()
        ),
    )
    monkeypatch.setattr(server_module, "resolve_engine_selector", lambda *_: "1")

    async def scenario() -> None:
        async with server_module.lifespan(MagicMock()) as state:
            assert state["mcp_config"].watch_enabled is True
        stop.assert_awaited_once()

    asyncio.run(scenario())
    start.assert_awaited_once()
    kwargs = start.await_args.kwargs
    assert kwargs["collections_path"] == cli_context.collections_path
    assert callable(kwargs["manifest_factory"])
