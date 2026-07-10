"""Search command for querying collections.

Thin command: parses args, resolves collections, runs the core search service,
and delegates all result rendering to ``search_render`` (thin command, fat
services — issue #119).
"""

import typer
from typing import Optional

from rich.markup import escape

from ...utils.logging import is_verbose_mode
from ...utils.simple_output import is_simple_output, print_json
from ...utils.console import console
from ...utils.context_managers import NoOpContext
from ...utils.progress_bar import create_phased_progress, build_search_phase_label
from ...utils.components.theme import (
    get_heading_style,
    get_accent_style,
    get_dim_style,
)
from ...utils.components import print_error
from .search_render import format_search_results, format_search_results_compact

app = typer.Typer(help="Search collections")


def _load_search_config():
    """Load ``[core.v1.search]`` so the CLI honors the same
    max_docs/max_chunks/score_threshold as MCP (foundation/6 E12 — the CLI
    used to hardcode from ``--limit`` only, so CLI and MCP disagreed on the
    same query). Falls back to model defaults when the section isn't
    registered/set, mirroring ``mcp/server.py::_get_config``.

    No defensive re-register needed here: ``resolve_collections_context``
    (already called earlier in this command) now re-registers app config
    itself right after resolving/resetting the singleton, so the specs are
    guaranteed to be present by the time this binds (foundation/6d root-cause
    fix — see ``runtime.py``).
    """
    from indexed.core.v1.config_models import CoreV1SearchConfig
    from indexed.config import ConfigService

    try:
        provider = ConfigService.instance().bind()
        return provider.get(CoreV1SearchConfig)
    except Exception:
        return CoreV1SearchConfig()


@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option(
        None, "--collection", "-c", help="Collection name to search"
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help=(
            "Number of results per collection (default: configured "
            "core.v1.search.max_docs)"
        ),
    ),
    compact: bool = typer.Option(
        False, "--compact", help="Show compact list instead of cards"
    ),
    no_content: bool = typer.Option(
        False, "--no-content", help="Hide content previews"
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
    """Search across collections using semantic similarity.

    Examples:
        indexed search "machine learning"              # Search all collections
        indexed search "bug fix" -c jira              # Search specific collection
        indexed search "API docs" --compact           # Compact list view
        indexed search "error handling" --no-content  # Hide content previews
    """
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import search as this_module

    svc_search = this_module.svc_search
    source_config_class = this_module.SourceConfig
    status_svc = this_module.status
    setup_root_logger_svc = this_module.setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger_svc(level_str=effective_level, json_mode=json_logs)

    simple = is_simple_output()

    from indexed.cli.composition import resolve_collections_context

    mode_override = ctx.obj.get("mode_override") if ctx.obj else None
    cli_ctx = resolve_collections_context(mode_override=mode_override)
    collections_path = str(cli_ctx.collections_path)

    # Display storage mode indicator (not in verbose/simple mode, to keep logs clean)
    if not is_verbose_mode() and not simple:
        from ...utils.storage_info import display_storage_mode_for_command

        display_storage_mode_for_command(console)

    # Determine collections to search
    if collection is None:
        # Search all collections
        all_statuses = status_svc(collections_path=collections_path)
        if not all_statuses:
            if simple:
                print_json({"error": "No collections found"})
                return
            console.print(
                f"\n[{get_dim_style()}]No collections found to search[/{get_dim_style()}]"
            )
            console.print(
                f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
            )
            return

        collections_to_search = [s.name for s in all_statuses]
        if not simple:
            # `query` is user input — escape before entering markup, the
            # surrounding style tags are ours (foundation/6c bug E2).
            console.print(
                f'\n[{get_heading_style()}]Searching for [{get_accent_style()}]"{escape(query)}"[/{get_accent_style()}] in {len(collections_to_search)} Collections:[/{get_heading_style()}]'
            )
    else:
        # Search specific collection
        statuses = status_svc([collection], collections_path=collections_path)
        if not statuses:
            if simple:
                # Simple/JSON output is a machine-readable envelope: report the
                # error as data (like the "no collections at all" branch above)
                # — but a JSON error body must still exit non-zero, never 0
                # (foundation/6 E1: never a traceback, never a silent success).
                print_json({"error": f"Collection '{collection}' not found"})
                raise typer.Exit(1)
            print_error(f"Collection '{collection}' not found")
            raise typer.Exit(1)

        collections_to_search = [collection]

    # Build search configs for all collections, reusing the status objects
    # already fetched above rather than re-querying per name: a second lookup
    # that came back empty (collection removed/corrupted between calls) used
    # to raw-IndexError on `coll_status.indexers[0]` (foundation/6 E1). A
    # per-collection guard here means one bad collection is skipped and
    # reported instead of crashing the whole search.
    status_by_name = {
        s.name: s for s in (all_statuses if collection is None else statuses)
    }
    search_configs = {}
    for coll_name in collections_to_search:
        coll_status = status_by_name.get(coll_name)
        if coll_status is None or not coll_status.indexers:
            print_error(f"Collection '{coll_name}' is unavailable, skipping")
            continue
        source_type = getattr(coll_status, "source_type", None) or "localFiles"
        search_configs[coll_name] = source_config_class(
            name=coll_name,
            type=source_type,
            base_url_or_path="",
            indexer=coll_status.indexers[0],
        )

    collections_to_search = [c for c in collections_to_search if c in search_configs]

    # Resolve effective search limits: an explicit --limit always wins (and
    # keeps the historical max_chunks = limit * 3 ratio); otherwise fall back
    # to the registered [core.v1.search] section so CLI and MCP agree on the
    # same query (foundation/6 E12).
    search_cfg = _load_search_config()
    effective_max_docs = limit if limit is not None else search_cfg.max_docs
    effective_max_chunks = limit * 3 if limit is not None else search_cfg.max_chunks
    score_threshold = search_cfg.score_threshold
    display_limit = effective_max_docs

    if not collections_to_search:
        # A specific collection was named but turned out unsearchable (corrupt
        # manifest / no indexers): that is a failed request, not just "nothing
        # to search" — exit non-zero. Searching ALL collections and finding
        # none searchable stays a soft no-op (exit 0), same as "no collections
        # found" above.
        named_collection_requested = collection is not None
        if simple:
            print_json({"error": "No searchable collections available"})
        else:
            console.print(
                f"[{get_dim_style()}]No searchable collections available[/{get_dim_style()}]"
            )
        if named_collection_requested:
            raise typer.Exit(1)
        return

    # Search each collection with phased progress
    results = {}

    if simple or is_verbose_mode():
        # Simple output / verbose mode: no progress display
        for coll_name in collections_to_search:
            with NoOpContext():
                result = svc_search(
                    query,
                    configs=[search_configs[coll_name]],
                    max_docs=effective_max_docs,
                    max_chunks=effective_max_chunks,
                    score_threshold=score_threshold,
                    include_matched_chunks=True,
                    collections_path=collections_path,
                )
                results.update(result)
    else:
        # Normal mode: phased progress display (consistent with Create/Update).
        # No section title: each phase label carries the full collection + query
        # context, so the plain (non-Rich) path — which ignores the title — keeps
        # it too. Multi-collection prints its summary headline above; single does
        # not (see #110/#88).
        with create_phased_progress() as phased:
            for coll_name in collections_to_search:
                phase_label = build_search_phase_label(query, coll_name)
                phased.start_phase(phase_label)
                result = svc_search(
                    query,
                    configs=[search_configs[coll_name]],
                    max_docs=effective_max_docs,
                    max_chunks=effective_max_chunks,
                    score_threshold=score_threshold,
                    include_matched_chunks=True,
                    collections_path=collections_path,
                )
                results.update(result)
                phased.finish_phase(phase_label)

    # Format and display results
    if simple:
        from indexed.mcp.formatting import format_search_results_for_llm

        print_json(format_search_results_for_llm(results, query))
    elif compact:
        format_search_results_compact(query, results, limit=display_limit)
    else:
        format_search_results(
            query, results, limit=display_limit, show_content=not no_content
        )


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "svc_search":
        from indexed.core.v1.engine import search

        return search
    elif name == "SourceConfig":
        from indexed.core.v1.engine import SourceConfig

        return SourceConfig
    elif name == "status":
        from indexed.core.v1.engine import status

        return status
    elif name == "setup_root_logger":
        from ...utils.logging import setup_root_logger

        return setup_root_logger
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
