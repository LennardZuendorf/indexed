"""Opt-in freshness for ``localFiles`` collections served by ``indexed-mcp run``.

The server otherwise serves whatever was on disk at the last ``index update``.
With ``[mcp] watch_enabled = true`` it also keeps the local collections that
existed at startup fresh: one reused ``run_watch_loop`` per collection, each on
its own thread (``asyncio.to_thread``) so a blocking update never stalls the
event loop. The update path's cold stack (LlamaIndex, the embedder) is imported
once, synchronously, before the first watcher thread exists — so neither another
watcher nor the search handler on its own thread can see it half-built (#358).

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

    async def stop(self) -> None:
        """Stop every loop and wait for its in-flight update to finish.

        The loops poll with a short sleep and re-check the event, so this
        returns in roughly one poll interval plus at most one running update
        (plus, on startup, the single cold-stack warm-up holding the gate) —
        never a hard kill that would abandon a half-written collection.
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


def warm_shared_stack() -> None:
    """Import the update path's cold stack on the caller's thread (#358).

    Nothing about a collection decides this import: the opening catch-up pass of
    every watcher needs it, and whichever pass runs first happens to pay it. So
    it is paid by ``start_watchers_if_enabled`` instead — on the thread that
    creates the watcher threads, before any of them (or the search handler that
    FastMCP runs on its own thread) exists. The import is then a single
    ``sys.modules`` population with no second importer alive to observe a
    half-initialised module.

    ``llama_index.embeddings.huggingface`` is the module that reported the
    partially initialized ``BaseEmbedding`` import, and importing it pulls
    ``llama_index.core``, ``transformers`` and ``sentence-transformers`` — the
    cold stack of both engines. Function-local for the same reason the rest of
    this module keeps its engine imports inside the thread body.
    """
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: F401


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

    def info(message: str) -> None:
        logger.info(f"collection watch [{target.collection}]: {message}")

    def error(message: str) -> None:
        logger.error(f"collection watch [{target.collection}]: {message}")

    try:
        code = watch_service.run_watch_loop(
            scan=target.scan,
            apply_update=run_pass,
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

    The cold stack is imported here, synchronously, before the first watcher
    thread exists (#358). That is the whole fix: an import only races when
    something else can import the same modules at the same time, and after this
    call there is nothing left to import — the catch-up passes find ``sys.modules``
    populated, and the search handler FastMCP will run on its own thread cannot
    observe a half-built ``llama_index`` because it is not served until startup
    returns.
    """
    if not getattr(mcp_config, "watch_enabled", False):
        return None

    targets = _plan_targets(collections_path, config_service)
    if not targets:
        logger.info("collection watch: enabled but no watchable local collection")
        return None

    try:
        warm_shared_stack()
    except Exception as exc:  # noqa: BLE001 — the pass reports it
        # The warm-up is an optimisation, never a new failure mode: each pass
        # below imports the same stack itself and is where a broken install has
        # to surface. One warning here beats N identical traces from threads.
        logger.warning(
            f"collection watch: stack warm-up failed ({exc}); "
            "each catch-up pass will import it itself"
        )

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
                )
            )
        )
    logger.info(
        "collection watch: watching "
        + ", ".join(target.collection for target, _ in targets)
    )
    return handle


__all__ = ["WatcherHandle", "start_watchers_if_enabled"]
