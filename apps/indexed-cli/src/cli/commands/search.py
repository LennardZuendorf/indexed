"""Search command for querying collections.

This command uses the core search service and the search_formatter to display
results beautifully with the card-based design system.
"""

import typer
from core.v1 import Index
from utils.logger import is_verbose_mode
from cli.formatters.search_formatter import (
    format_search_results,
    format_search_results_compact,
)
from cli.components import SearchStatus
from cli.utils.console import console

app = typer.Typer(help="Search collections")


class _NoOpContext:
    """No-op context manager for verbose mode (no spinner)."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option(None, "--collection", "-c", help="Collection name to search"),
    limit: int = typer.Option(5, "--limit", "-l", help="Number of results to display per collection"),
    compact: bool = typer.Option(False, "--compact", help="Show compact list instead of cards"),
    no_content: bool = typer.Option(False, "--no-content", help="Hide content previews"),
):
    """Search across collections using semantic similarity.
    
    Examples:
        indexed search "machine learning"              # Search all collections
        indexed search "bug fix" -c jira              # Search specific collection  
        indexed search "API docs" --compact           # Compact list view
        indexed search "error handling" --no-content  # Hide content previews
    """
    index = Index()
    
    # Perform search with matched chunks
    # Note: Index.search doesn't expose these params, so we need to use the service directly
    from core.v1.engine.services import search as search_service
    
    # Build search config if specific collection requested
    configs = None
    if collection:
        from core.v1.engine.services import status
        statuses = status([collection])
        if statuses:
            from core.v1.engine.services import SourceConfig
            coll_status = statuses[0]
            configs = [
                SourceConfig(
                    name=collection,
                    type="localFiles",
                    base_url_or_path="",
                    indexer=coll_status.indexers[0]
                )
            ]
    
    # Execute search with spinner (default) or verbose logs
    # The OperationStatus context manager captures INFO logs and shows them in spinner
    # Format: [spinner] Searching "query": [log message]
    # In verbose mode, logs go directly to console via Rich formatting
    operation_desc = f'Searching "{query}"'
    context = SearchStatus(console, operation_desc) if not is_verbose_mode() else _NoOpContext()
    
    with context:
        results = search_service(
            query,
            configs=configs,
            max_docs=limit,
            max_chunks=limit * 3,
            include_matched_chunks=True,
        )
    
    # Format and display results
    if compact:
        format_search_results_compact(query, results, limit=limit)
    else:
        format_search_results(query, results, limit=limit, show_content=not no_content)
