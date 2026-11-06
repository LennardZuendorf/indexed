"""``index watch`` — keep one collection fresh while the command runs.

Opt-in by construction: nothing starts this loop except typing the command, it
runs in the foreground, and it dies with the process. Only ``localFiles``
collections can be watched — the other connectors have no local source tree.
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from loguru import logger

from ...utils.components import print_error
from ...utils.console import console
from ...watch_config import resolve_watch_config

app = typer.Typer(help="Watch a collection and update it as its files change")


@app.command()
def watch(
    ctx: typer.Context,
    collection: str = typer.Argument(
        None, help="Collection to watch (must read from a local directory)"
    ),
    collection_opt: Annotated[
        Optional[str],
        typer.Option(
            "--collection",
            "-c",
            help="Collection to watch (alias for the positional argument).",
        ),
    ] = None,
    debounce: Annotated[
        Optional[float],
        typer.Option(
            "--debounce",
            "-d",
            help=(
                "Seconds of quiet after the last change before one update runs. "
                "Default: watch.debounce_seconds (2.0)."
            ),
        ),
    ] = None,
    poll_interval: Annotated[
        Optional[float],
        typer.Option(
            "--poll-interval",
            help=(
                "Seconds between scans of the source tree. "
                "Default: watch.poll_interval_seconds (2.0)."
            ),
        ),
    ] = None,
    once: bool = typer.Option(
        False,
        "--once",
        help="Run a single update pass and exit instead of watching.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose (INFO) logging",
        rich_help_panel="Logging",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON (structured)",
        rich_help_panel="Logging",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        rich_help_panel="Logging",
    ),
):
    """Keep a collection fresh: poll its source tree, one update per change burst.

    Runs in the foreground until Ctrl-C — no background daemon is started. If the
    watched source path disappears (unmounted, renamed, deleted) the loop logs an
    error and keeps the last good index instead of running an update that would
    empty the collection; it resumes when the path returns.
    """
    if collection_opt is not None:
        if collection and collection != collection_opt:
            print_error(
                "Pass the collection once — as a positional OR --collection, not both."
            )
            raise typer.Exit(1)
        collection = collection_opt
    if not collection:
        print_error("Name the collection to watch: indexed index watch <collection>")
        raise typer.Exit(1)

    from ...composition import resolve_collections_context, wiring_kwargs_for_update
    from ...utils.logging import setup_root_logger
    from indexed.core.engine import SourceConfig, status as svc_status
    from indexed.core.engine import update as run_update
    from . import watch_service
    from .update_service import _read_manifest_reader_config

    setup_root_logger(
        level_str=log_level or ("INFO" if verbose else None), json_mode=json_logs
    )

    mode_override = ctx.obj.get("mode_override") if ctx.obj else None
    cli_ctx = resolve_collections_context(mode_override=mode_override)
    collections_path = str(cli_ctx.collections_path)
    config_service = cli_ctx.config_service
    engine_flag = ctx.obj.get("engine") if ctx.obj else None

    settings = resolve_watch_config(config_service)
    debounce_seconds = (
        debounce if debounce is not None else float(settings.debounce_seconds)
    )
    poll_seconds = (
        poll_interval
        if poll_interval is not None
        else float(settings.poll_interval_seconds)
    )

    statuses = svc_status([collection], collections_path=collections_path)
    if not statuses:
        print_error(f"Collection '{collection}' not found")
        raise typer.Exit(1)
    coll_status = statuses[0]
    source_type = getattr(coll_status, "source_type", None) or "localFiles"
    if source_type != "localFiles":
        print_error(
            f"Collection '{collection}' reads from {source_type}, not a local "
            "source tree — only localFiles collections can be watched."
        )
        raise typer.Exit(2)

    reader_cfg = _read_manifest_reader_config(collection, collections_path)
    base_path = str(reader_cfg.get("basePath") or "")
    if not base_path or not Path(base_path).is_dir():
        print_error(
            f"Source path '{base_path or '<unset>'}' of '{collection}' is not a "
            "directory — refusing to watch: an unreachable source would empty the "
            "collection on the next update."
        )
        raise typer.Exit(2)

    excluded_dirs = tuple(reader_cfg.get("excludedDirs") or ())
    respect_gitignore = bool(reader_cfg.get("respectGitignore", True))

    if not coll_status.indexers:
        print_error(f"Collection '{collection}' has no indexers configured")
        raise typer.Exit(1)
    source_config = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path="",
        indexer=coll_status.indexers[0],
    )
    update_wiring = wiring_kwargs_for_update(cli_ctx)
    if engine_flag is not None:
        update_wiring["engine"] = engine_flag

    def scan() -> "watch_service.WatchSignature | None":
        return watch_service.signature_for(
            base_path,
            excluded_dirs=excluded_dirs,
            respect_gitignore=respect_gitignore,
        )

    def apply_update() -> None:
        # Clean overlay per pass, mirroring run_update_loop (R3): the manifest
        # factory re-applies this collection's stored settings via from_manifest.
        config_service.clear_overlay()
        run_update([source_config], **update_wiring)

    if once:
        if scan() is None:
            print_error(f"Source path '{base_path}' is not readable")
            raise typer.Exit(2)
        apply_update()
        console.print("Update pass finished.")
        return

    console.print(
        f"Watching {base_path} for '{collection}' "
        f"(debounce {debounce_seconds:g}s, poll {poll_seconds:g}s) — Ctrl-C to stop."
    )
    try:
        exit_code = watch_service.run_watch_loop(
            scan=scan,
            apply_update=apply_update,
            debounce_seconds=debounce_seconds,
            poll_interval_seconds=poll_seconds,
            log_info=logger.info,
            log_error=logger.error,
        )
    except KeyboardInterrupt:
        console.print("Stopped watching.")
        return
    console.print("Stopped watching.")
    if exit_code != 0:
        raise typer.Exit(exit_code)
