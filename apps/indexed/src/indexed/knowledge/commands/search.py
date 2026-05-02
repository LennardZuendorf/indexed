"""Search command for querying collections.

This command uses the core search service and the search_formatter to display
results beautifully with the card-based design system.
"""

import typer
from typing import Dict, Any, List, Optional, TypedDict, TYPE_CHECKING

# Raw Panel needed — free-text excerpt content doesn't fit card components
from rich.panel import Panel

if TYPE_CHECKING:
    pass

from ...utils.logging import is_verbose_mode
from ...utils.simple_output import is_simple_output, print_json
from ...utils.console import console
from ...utils.context_managers import NoOpContext
from ...utils.progress_bar import create_phased_progress
from ...utils.components.theme import get_heading_style, get_accent_style
from ...utils.components import (
    create_summary,
    create_detail_card,
    get_card_border_style,
    get_card_padding,
    get_secondary_style,
    get_dim_style,
    print_error,
    print_warning,
)
from ...utils.components.theme import get_detail_card_width

app = typer.Typer(help="Search collections")


class ChunkInfo(TypedDict):
    collection: str
    doc_id: str
    path: str
    chunk: Dict[str, Any]
    chunk_index: int


# --- SEARCH FORMATTER FUNCTIONS (moved from search_formatter.py) ---


def format_search_results(
    query: str,
    results: Dict[str, Any],
    limit: int = 5,
    show_content: bool = True,
) -> None:
    """Display search results with single top result and compact list of others.

    Shows the single most relevant chunk with full content excerpt in a card,
    then lists the next 4 matches in a compact format showing collection/doc/chunk.

    Args:
        query: The search query
        results: Dictionary with collection names as keys and result data as values
        limit: Maximum number of total results to show (unused, kept for compatibility)
        show_content: Whether to show content previews
    """
    console.print()

    if not show_content:
        # If content hidden, use compact format
        _show_all_results_compact(results, limit)
        return

    # Collect all chunks across all collections with their metadata
    all_chunks: List[ChunkInfo] = []
    total_docs = 0

    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            continue

        documents = collection_results.get("results", [])
        total_docs += len(documents)

        for doc in documents:
            doc_id = doc.get("id", "Unknown")
            path = doc.get("path") or doc.get("url", "")
            matched_chunks = doc.get("matchedChunks", []) or doc.get(
                "matched_chunks", []
            )

            for i, chunk in enumerate(matched_chunks):
                all_chunks.append(
                    ChunkInfo(
                        collection=collection_name,
                        doc_id=doc_id,
                        path=path,
                        chunk=chunk,
                        chunk_index=i + 1,  # 1-indexed for display
                    )
                )

    if not all_chunks:
        print_warning(
            f'No results found for "{query}". '
            f"Try broadening your search terms or checking collection contents."
        )
        console.print()
        return

    # Sort chunks by score (ascending - lower is better for distance)
    all_chunks.sort(key=lambda x: x["chunk"].get("score", 999), reverse=False)

    # Show top result with split meta/excerpt cards
    console.print(
        f"[{get_heading_style()}]Best Matched Search Result:[/{get_heading_style()}]"
    )
    console.print()
    _show_top_result_split_cards(all_chunks[0])

    # Show next 4 results in compact format
    if len(all_chunks) > 1:
        console.print()
        console.print(
            f"[{get_heading_style()}]Other Search Query Matches[/{get_heading_style()}]"
        )
        console.print()

        for chunk_info in all_chunks[1:5]:  # Show up to 4 more
            _show_compact_match(chunk_info)

    # Summary
    console.print()
    summary = create_summary(
        "Search Result",
        f"Found {len(all_chunks)} matching chunks across {total_docs} documents",
    )
    console.print(summary)
    console.print()


def _show_top_result_split_cards(chunk_info: ChunkInfo) -> None:
    """Show the top result chunk in two cards: Meta and Excerpt."""

    collection = chunk_info["collection"]
    doc_id = chunk_info["doc_id"]
    chunk = chunk_info["chunk"]
    chunk_index = chunk_info["chunk_index"]

    # --- METADATA CARD ---
    meta_rows = []
    meta_rows.append(("Collection", collection))
    meta_rows.append(("Document", doc_id))

    score = chunk.get("score")
    score_str = (
        f"{score:.4f}"
        if isinstance(score, float)
        else (str(score) if score is not None else "N/A")
    )
    meta_rows.append(("Score", score_str))
    meta_rows.append(("Chunk", str(chunk_index)))

    # Only include match id if available
    chunk_id = chunk.get("id")
    if chunk_id:
        meta_rows.append(("Match ID", chunk_id))

    meta_card = create_detail_card(title="Top Result Meta", rows=meta_rows)
    console.print(meta_card)

    # --- EXCERPT CARD ---
    # Get chunk excerpt
    chunk_content_obj = chunk.get("content", {})
    if isinstance(chunk_content_obj, dict):
        chunk_content = chunk_content_obj.get("indexedData", "")
    else:
        chunk_content = str(chunk_content_obj)
    excerpt = chunk_content.strip() if chunk_content else ""
    max_length = 1500
    display_excerpt = (
        excerpt if len(excerpt) <= max_length else excerpt[:max_length] + "..."
    )

    # Use a subtle dim/muted style for the excerpt card with same width as meta card
    excerpt_panel = Panel(
        f"[{get_dim_style()}]{display_excerpt}[/{get_dim_style()}]"
        if excerpt
        else f"[{get_dim_style()}][No excerpt available][/{get_dim_style()}]",
        title="Top Result Excerpt",
        border_style=get_card_border_style(),
        padding=get_card_padding(),
        style=get_secondary_style(),
        width=get_detail_card_width(),  # Match the meta card width
    )
    console.print(excerpt_panel)


def _show_compact_match(chunk_info: ChunkInfo) -> None:
    """Show a compact single-line match."""
    collection = chunk_info["collection"]
    doc_id = chunk_info["doc_id"]
    chunk = chunk_info["chunk"]
    chunk_index = chunk_info["chunk_index"]
    score = chunk.get("score", "N/A")
    if isinstance(score, float):
        chunk_score = f"{score:.4f}"
    else:
        chunk_score = str(score)

    # Format: collection / document / part / match_id
    console.print(
        f"  • [{get_accent_style()}]{collection}[/{get_accent_style()}] / "
        f"{doc_id} / "
        f"[{get_dim_style()}]Chunk {chunk_index}[/{get_dim_style()}] / "
        f"[{get_dim_style()}]{chunk_score}[/{get_dim_style()}]"
    )


def _show_all_results_compact(results: Dict[str, Any], limit: int) -> None:
    """Show all results in compact format when content is hidden."""
    total_results = 0

    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            continue

        documents = collection_results.get("results", [])
        if not documents:
            continue

        total_results += len(documents)

        # Collection header
        console.print(
            f"[{get_accent_style()}]{collection_name}[/{get_accent_style()}] [{get_dim_style()}]({len(documents)} results)[/{get_dim_style()}]"
        )

        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            console.print(f"  {i}. {doc_id}")

        console.print()

    # Summary
    console.print()
    if total_results > 0:
        console.print(create_summary("Search Result", f"{total_results} results"))
    else:
        console.print(f"[{get_dim_style()}]No results found[/{get_dim_style()}]")

    console.print()


def format_search_results_compact(
    query: str,
    results: Dict[str, Any],
    limit: int = 10,
) -> None:
    """Display search results in compact list format.

    Args:
        query: The search query
        results: Dictionary with collection names as keys and result data as values
        limit: Maximum number of results to show per collection
    """

    total_results = 0

    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            continue

        documents = collection_results.get("results", [])
        if not documents:
            continue

        total_results += len(documents)

        # Collection header
        console.print(
            f"[{get_accent_style()}]{collection_name}[/{get_accent_style()}] [{get_dim_style()}]({len(documents)} results)[/{get_dim_style()}]"
        )

        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            score = doc.get("score")

            if score is not None:
                score_str = (
                    f" [{score:.4f}]" if isinstance(score, float) else f" [{score}]"
                )
                console.print(
                    f"  {i}. {doc_id}[{get_dim_style()}]{score_str}[/{get_dim_style()}]"
                )
            else:
                console.print(f"  {i}. {doc_id}")

        console.print()

    # Summary
    console.print()
    if total_results > 0:
        console.print(create_summary("Search Result", f"{total_results} results"))
    else:
        console.print(f"[{get_dim_style()}]No results found[/{get_dim_style()}]")

    console.print()


def _normalize_v2_search(raw: dict) -> dict:
    """Convert v2 search output to v1-compatible display format.

    v2 single-collection:  {"collectionName": name, "results": [...]}
    v2 multi-collection:   {"query": ..., "collections": [{...}, ...]}
    CLI display expects:   {coll_name: {"results": [...]}}
    """
    if "collections" in raw:
        return {
            item["collectionName"]: {"results": item.get("results", [])}
            for item in raw["collections"]
        }
    # Single-collection result
    return {raw["collectionName"]: {"results": raw.get("results", [])}}


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option(
        None, "--collection", "-c", help="Collection name to search"
    ),
    limit: int = typer.Option(
        5, "--limit", "-l", help="Number of results to display per collection"
    ),
    compact: bool = typer.Option(
        False, "--compact", help="Show compact list instead of cards"
    ),
    no_content: bool = typer.Option(
        False, "--no-content", help="Hide content previews"
    ),
    engine: Optional[str] = typer.Option(
        None,
        "--engine",
        help="Engine version: v1 (default) or v2 (LlamaIndex-powered)",
        case_sensitive=False,
        rich_help_panel="Engine",
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
    from ...services.engine_router import get_effective_engine

    active_engine = get_effective_engine(engine)

    index_class = this_module.Index
    svc_search = this_module.svc_search
    source_config_class = this_module.SourceConfig
    status_svc = this_module.status
    setup_root_logger_svc = this_module.setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger_svc(level_str=effective_level, json_mode=json_logs)

    index_class()

    simple = is_simple_output()

    # Prefer local collections over global
    from ...utils.storage_info import resolve_preferred_collections_path

    preferred_path = str(resolve_preferred_collections_path())

    # Display storage mode indicator (not in verbose/simple mode, to keep logs clean)
    if not is_verbose_mode() and not simple:
        from ...utils.storage_info import display_storage_mode_for_command

        display_storage_mode_for_command(console)

    # Determine collections to search
    from pathlib import Path

    preferred_dir = Path(preferred_path)

    if active_engine == "v2":
        from indexed_config import ConfigService
        from core.v2.config import (
            CoreV2SearchConfig,
            CoreV2EmbeddingConfig,
            register_config as _register_v2_config,
        )

        _cs = ConfigService.instance()
        _register_v2_config(_cs)  # idempotent — ensure specs are registered
        _provider = _cs.bind()
        _v2_search_cfg = _provider.get(CoreV2SearchConfig)
        _v2_embed_cfg = _provider.get(CoreV2EmbeddingConfig)
        svc_search_v2 = this_module.svc_search_v2

    if collection is None:
        # Search all collections
        if active_engine == "v2":
            from core.v2.services import status as v2_status

            all_statuses = v2_status(collections_dir=preferred_dir)
        else:
            all_statuses = status_svc(collections_path=preferred_path)
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
            console.print(
                f'\n[{get_heading_style()}]Searching for [{get_accent_style()}]"{query}"[/{get_accent_style()}] in {len(collections_to_search)} Collections:[/{get_heading_style()}]'
            )
    else:
        # Search specific collection
        if active_engine == "v2":
            from core.v2.services import status as v2_status

            statuses = v2_status([collection], collections_dir=preferred_dir)
        else:
            statuses = status_svc([collection], collections_path=preferred_path)
        if not statuses:
            if simple:
                print_json({"error": f"Collection '{collection}' not found"})
                raise typer.Exit(1)
            print_error(f"Collection '{collection}' not found")
            raise typer.Exit(1)

        collections_to_search = [collection]
        if not simple:
            console.print(
                f'\n[{get_heading_style()}]Searching for [{get_accent_style()}]"{query}"[/{get_accent_style()}] in 1 Collection:[/{get_heading_style()}]'
            )

    # Build search configs for all collections (v1 only — v2 uses name-based lookup)
    search_configs = {}
    if active_engine != "v2":
        for coll_name in collections_to_search:
            coll_status = status_svc([coll_name], collections_path=preferred_path)[0]
            search_configs[coll_name] = source_config_class(
                name=coll_name,
                type="localFiles",
                base_url_or_path="",
                indexer=coll_status.indexers[0],
            )

    # Search each collection with phased progress
    results = {}

    if simple or is_verbose_mode():
        # Simple output / verbose mode: no progress display
        for coll_name in collections_to_search:
            with NoOpContext():
                if active_engine == "v2":
                    raw = svc_search_v2(
                        query,
                        configs=[
                            source_config_class(
                                name=coll_name, type="localFiles", base_url_or_path=""
                            )
                        ],
                        max_docs=_v2_search_cfg.max_docs,
                        max_chunks=_v2_search_cfg.max_chunks,
                        include_matched_chunks=_v2_search_cfg.include_matched_chunks,
                        embed_model_name=_v2_embed_cfg.model_name,
                        collections_dir=preferred_dir,
                    )
                    results.update(_normalize_v2_search(raw))
                else:
                    result = svc_search(
                        query,
                        configs=[search_configs[coll_name]],
                        max_docs=limit,
                        max_chunks=limit * 3,
                        include_matched_chunks=True,
                        collections_path=preferred_path,
                    )
                    results.update(result)
    else:
        # Normal mode: phased progress display (consistent with Create/Update)
        heading = get_heading_style()
        accent = get_accent_style()
        title = (
            f"[{heading}]Searching collection: [{accent}]{query}[/{accent}][/{heading}]"
        )

        with create_phased_progress(title=title) as phased:
            for coll_name in collections_to_search:
                phased.start_phase(f"Searching {coll_name}")
                result = svc_search(
                    query,
                    configs=[search_configs[coll_name]],
                    max_docs=limit,
                    max_chunks=limit * 3,
                    include_matched_chunks=True,
                    collections_path=preferred_path,
                )
                results.update(result)
                phased.finish_phase(f"Searching {coll_name}")

    # Format and display results
    if simple:
        from ...mcp.formatting import format_search_results_for_llm

        print_json(format_search_results_for_llm(results, query))
    elif compact:
        format_search_results_compact(query, results, limit=limit)
    else:
        format_search_results(query, results, limit=limit, show_content=not no_content)


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "Index":
        from core.v1 import Index

        return Index
    elif name == "svc_search":
        from core.v1.engine.services import search

        return search
    elif name == "svc_search_v2":
        from core.v2.services import search

        return search
    elif name == "SourceConfig":
        from core.v1.engine.services import SourceConfig

        return SourceConfig
    elif name == "status":
        from core.v1.engine.services import status

        return status
    elif name == "setup_root_logger":
        from ...utils.logging import setup_root_logger

        return setup_root_logger
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
