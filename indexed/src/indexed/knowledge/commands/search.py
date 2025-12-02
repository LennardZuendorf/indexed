"""Search command for querying collections.

This command uses the core search service and the search_formatter to display
results beautifully with the card-based design system.
"""

import typer
from typing import Dict, Any, List, Optional, TypedDict
from rich.panel import Panel
from core.v1 import Index
from core.v1.engine.services import search as search_service, SourceConfig, status
from ...utils.logging import is_verbose_mode
from ...utils.console import console
from ...utils.context_managers import NoOpContext, suppress_core_output
from ...utils.progress_bar import create_operation_progress
from ...utils.components.theme import get_heading_style, get_accent_style
from ...utils.components import (
    create_summary,
    create_detail_card,
    get_card_border_style,
    get_card_padding,
    get_secondary_style,
    get_default_style,
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
        console.print(
            f"[{get_secondary_style()}]No results found[/{get_secondary_style()}]"
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
        f"[dim]{display_excerpt}[/dim]"
        if excerpt
        else "[dim][No excerpt available][/dim]",
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
        f"[dim]Chunk {chunk_index}[/dim] / "
        f"[dim]{chunk_score}[/dim]"
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
            f"[{get_accent_style()}]{collection_name}[/{get_accent_style()}] [dim]({len(documents)} results)[/dim]"
        )

        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            console.print(f"  {i}. {doc_id}")

        console.print()

    # Summary
    if total_results > 0:
        console.print(
            f"[{get_accent_style()}]Total:[/{get_accent_style()}] {total_results} results"
        )
    else:
        console.print(
            f"[{get_secondary_style()}]No results found[/{get_secondary_style()}]"
        )

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
            f"[bold]{collection_name}[/bold] [dim]({len(documents)} results)[/dim]"
        )

        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            score = doc.get("score")

            if score is not None:
                score_str = (
                    f" [{score:.4f}]" if isinstance(score, float) else f" [{score}]"
                )
                console.print(f"  {i}. {doc_id}[dim]{score_str}[/dim]")
            else:
                console.print(f"  {i}. {doc_id}")

        console.print()

    # Summary
    if total_results > 0:
        console.print(
            f"[{get_accent_style()}]Total:[/{get_accent_style()}] {total_results} results"
        )
    else:
        console.print(
            f"[{get_secondary_style()}]No results found[/{get_secondary_style()}]"
        )

    console.print()


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
    from ...utils.logging import setup_root_logger
    
    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)
    
    Index()

    # Determine collections to search
    if collection is None:
        # Search all collections
        all_statuses = status()
        if not all_statuses:
            console.print("\nNo collections found to search")
            return

        collections_to_search = [s.name for s in all_statuses]
        console.print(
            f'\n[{get_heading_style()}]Searching for [bold {get_accent_style()}]"{query}"[/{get_accent_style()}] in {len(collections_to_search)} Collections:[/{get_heading_style()}]'
        )
    else:
        # Search specific collection
        statuses = status([collection])
        if not statuses:
            typer.echo(f"❌ Collection '{collection}' not found")
            raise typer.Exit(1)

        collections_to_search = [collection]
        console.print(
            f'\n[{get_heading_style()}]Searching for [{get_accent_style()}]"{query}"[/{get_accent_style()}] in 1 Collection:[/{get_heading_style()}]'
        )

    # Build search configs for all collections
    search_configs = []
    for coll_name in collections_to_search:
        coll_status = status([coll_name])[0]
        config = SourceConfig(
            name=coll_name,
            type="localFiles",  # Default type, not used in search
            base_url_or_path="",  # Not used in search
            indexer=coll_status.indexers[0],  # Get from collection status
        )
        search_configs.append(config)

    # Search each collection with individual progress
    results = {}
    for coll_name in collections_to_search:
        # Get collection status to build proper SourceConfig
        coll_status = status([coll_name])[0]
        config = SourceConfig(
            name=coll_name,
            type="localFiles",  # Default type, not used in search
            base_url_or_path="",  # Not used in search
            indexer=coll_status.indexers[0],  # Get from collection status
        )

        operation_desc = f"[{get_default_style()}]Searching collection: [{get_accent_style()}]{coll_name}[/{get_accent_style()}][/{get_default_style()}]"

        if is_verbose_mode():
            # Verbose mode: show core logs directly
            with NoOpContext():
                result = search_service(
                    query,
                    configs=[config],
                    max_docs=limit,
                    max_chunks=limit * 3,
                    include_matched_chunks=True,
                )
                results.update(result)
        else:
            # Normal mode: use centralized progress tracking
            with create_operation_progress(operation_desc) as (
                progress,
                task_id,
                callback,
            ):
                # Suppress all core output and call search service
                with suppress_core_output():
                    result = search_service(
                        query,
                        configs=[config],
                        max_docs=limit,
                        max_chunks=limit * 3,
                        include_matched_chunks=True,
                        progress_callback=callback,
                    )
                    results.update(result)

    # Format and display results
    if compact:
        format_search_results_compact(query, results, limit=limit)
    else:
        format_search_results(query, results, limit=limit, show_content=not no_content)
