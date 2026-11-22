"""Opt-in freshness for ``localFiles`` collections served by ``indexed-mcp run``.

The server otherwise serves whatever was on disk at the last ``index update``.
With ``[mcp] watch_enabled = true`` it also keeps the local collections that
existed at startup fresh: one reused ``run_watch_loop`` per collection, each on
its own thread (``asyncio.to_thread``) so a blocking update never stalls the
event loop. The opening catch-up pass of every collection is serialised behind
one gate so the process's first LlamaIndex/embedder import has exactly one
owner; every pass after that is independent (#358).

Scope is fixed at startup on purpose. A collection created while the server
runs is picked up on the next restart — the set is never re-planned behind the
user, and a collection removed underneath simply fails its update pass and is
logged, exactly like the CLI watcher.

Nothing here runs unless the lifespan asks for it: the module itself imports
only stdlib and ``loguru``, and every engine/connector import happens inside the
thread body, so a server with the gate off pays nothing beyond reading one
config field.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class WatcherHandle:
    """The watcher tasks of one running server, and their shared signals."""

    stop_event: threading.Event = field(default_factory=threading.Event)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    # One gate and one flag for the *opening* catch-up pass of every watcher
    # (issue #358). The first pass is the process's first heavy import —
    # LlamaIndex and the embedder — so exactly one thread runs it; a thread
    # that lost that race used to get a half-initialised module, which stays in
    # ``sys.modules`` and fails every later pass for the whole process.
    first_pass_gate: threading.Lock = field(default_factory=threading.Lock)
    stack_warm: threading.Event = field(default_factory=threading.Event)

    async def stop(self) -> None:
        """Stop every loop and wait for its in-flight update to finish.

        The loops poll with a short sleep and re-check the event, so this
        returns in roughly one poll interval plus at most one running update
        (plus, on startup, the single pass holding the opening gate) — never a
        hard kill that would abandon a half-written collection.
        """
        self.stop_event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)


def _plan_targets(
    collections_path: str | Path, config_service: Any
) -> list[tuple[Any, Any]]:
    """Return ``(WatchTarget, SourceConfig)`` for every local collection.

    Enumerates once, at startup. Non-``localFiles`` collections and collections
    whose source path is missing/unreadable are skipped with a warning: a
    missing source must never reach ``update``, because that would read as
    "every file was deleted" and empty the collection.
    """
    from indexed.cli.knowledge.commands import watch_service
    from indexed.core.engine import SourceConfig
    from indexed.core.engine import status as svc_status

    try:
        statuses = svc_status(collections_path=str(collections_path))
    except Exception as exc:  # noqa: BLE001 — a broken store must not kill the server
        logger.warning(f"collection watch: could not list collections ({exc})")
        return []

    planned: list[tuple[Any, Any]] = []
    for coll in statuses:
        name = getattr(coll, "name", None)
        if not name:
            continue
        source_type = getattr(coll, "source_type", None) or "localFiles"
        if source_type != "localFiles":
            continue
        indexers = getattr(coll, "indexers", None) or ()
        if not indexers:
            logger.warning(f"collection watch: '{name}' has no indexers — not watched")
            continue
        target = watch_service.resolve_watch_target(
            name, collections_path, config_service=config_service
        )
        if target is None:
            logger.warning(
                f"collection watch: source path of '{name}' is not a directory — "
                "not watched (an unreachable source would empty the collection)"
            )
            continue
        planned.append(
            (
                target,
                SourceConfig(
                    name=name,
                    type=source_type,
                    base_url_or_path="",
                    indexer=indexers[0],
                ),
            )
        )
    return planned


def _watch_one(
    target: Any,
    source_config: Any,
    *,
    collections_path: str,
    config_service: Any,
    manifest_factory: Any,
    debounce_seconds: float,
    poll_interval_seconds: float,
    stop_event: threading.Event,
    first_pass_gate: threading.Lock,
    stack_warm: threading.Event,
) -> None:
    """Run one collection's loop to completion (this is the thread body)."""
    from indexed.cli.knowledge.commands import watch_service
    from indexed.core.engine import update as run_update

    def run_pass() -> None:
        # Clean overlay per pass, mirroring ``index update``/``index watch``:
        # the manifest factory re-applies this collection's stored settings.
        config_service.clear_overlay()
        run_update(
            [source_config],
            collections_path=collections_path,
            manifest_factory=manifest_factory,
        )

    def apply_update() -> None:
        """Apply one pass, letting the opening one warm the stack alone (#358).

        Every collection that existed at startup runs its catch-up immediately,
        so with N collections N threads entered LlamaIndex's lazy import (and
        the embedder load) at the same instant. Serialising only the first pass
        gives the process one owner of that import; once the stack is warm the
        loops are independent again, and a thread waiting here waits at most one
        update pass — never a hard block on the loop.
        """
        if stack_warm.is_set():
            run_pass()
            return
        with first_pass_gate:
            already_warm = stack_warm.is_set()
            if not already_warm:
                try:
                    run_pass()
                finally:
                    # The gate serialises the first *attempt*, not the first
                    # success: one broken collection must not queue every other
                    # collection's retries behind it.
                    stack_warm.set()
        if already_warm:
            run_pass()

    def info(message: str) -> None:
        logger.info(f"collection watch [{target.collection}]: {message}")

    def error(message: str) -> None:
        logger.error(f"collection watch [{target.collection}]: {message}")

    try:
        code = watch_service.run_watch_loop(
            scan=target.scan,
            apply_update=apply_update,
            debounce_seconds=debounce_seconds,
            poll_interval_seconds=poll_interval_seconds,
            log_info=info,
            log_error=error,
            stop=stop_event,
        )
    except Exception as exc:  # noqa: BLE001 — one collection must not kill the server
        logger.error(f"collection watch [{target.collection}] stopped: {exc}")
        return
    if code != 0:
        logger.error(
            f"collection watch [{target.collection}] ended with code {code}; "
            "the collection is no longer fresh until the server restarts"
        )


async def start_watchers_if_enabled(
    mcp_config: Any,
    *,
    collections_path: str | Path,
    config_service: Any,
    manifest_factory: Any,
) -> WatcherHandle | None:
    """Start one watcher per existing local collection when the gate is on.

    Returns ``None`` when the gate is off — no import, no thread, no task — so a
    default server's startup and behaviour are exactly what they were before.
    """
    if not getattr(mcp_config, "watch_enabled", False):
        return None

    targets = _plan_targets(collections_path, config_service)
    if not targets:
        logger.info("collection watch: enabled but no watchable local collection")
        return None

    handle = WatcherHandle()
    for target, source_config in targets:
        handle.tasks.append(
            asyncio.create_task(
                asyncio.to_thread(
                    _watch_one,
                    target,
                    source_config,
                    collections_path=str(collections_path),
                    config_service=config_service,
                    manifest_factory=manifest_factory,
                    debounce_seconds=float(mcp_config.watch_debounce_seconds),
                    poll_interval_seconds=float(mcp_config.watch_poll_interval_seconds),
                    stop_event=handle.stop_event,
                    first_pass_gate=handle.first_pass_gate,
                    stack_warm=handle.stack_warm,
                )
            )
        )
    logger.info(
        "collection watch: watching "
        + ", ".join(target.collection for target, _ in targets)
    )
    return handle


__all__ = ["WatcherHandle", "start_watchers_if_enabled"]
