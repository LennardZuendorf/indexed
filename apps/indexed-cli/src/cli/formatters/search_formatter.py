"""Formatter for displaying search results with Rich.

This module provides presentation-layer logic for formatting search results
into beautiful Rich console output using the centralized design system.
"""

from typing import Dict, Any, List
from rich.panel import Panel
from rich.console import Group
from rich.text import Text

from cli.utils.console import console
from cli.components import (
    create_info_row,
    create_summary,
    create_detail_card,
    ACCENT_STYLE,
    CARD_BORDER_STYLE,
    CARD_PADDING,
    SECONDARY_STYLE,
)


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
    
    # Header with query
    console.print(f"[{ACCENT_STYLE}]Search:[/{ACCENT_STYLE}] {query}")
    console.print()
    
    if not show_content:
        # If content hidden, use compact format
        _show_all_results_compact(results, limit)
        return
    
    # Collect all chunks across all collections with their metadata
    all_chunks = []
    total_docs = 0
    
    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            continue
        
        documents = collection_results.get("results", [])
        total_docs += len(documents)
        
        for doc in documents:
            doc_id = doc.get("id", "Unknown")
            path = doc.get("path") or doc.get("url", "")
            matched_chunks = doc.get("matchedChunks", []) or doc.get("matched_chunks", [])
            
            for i, chunk in enumerate(matched_chunks):
                all_chunks.append({
                    "collection": collection_name,
                    "doc_id": doc_id,
                    "path": path,
                    "chunk": chunk,
                    "chunk_index": i + 1,  # 1-indexed for display
                })
    
    if not all_chunks:
        console.print(f"[{SECONDARY_STYLE}]No results found[/{SECONDARY_STYLE}]")
        console.print()
        return
    
    # Sort chunks by score (descending - lower is better for distance)
    all_chunks.sort(key=lambda x: x["chunk"].get("score", 999), reverse=False)
    
    # Show top result with full excerpt
    console.print(f"[{ACCENT_STYLE}]Best Match[/{ACCENT_STYLE}]")
    console.print()
    _show_top_result_card(all_chunks[0])
    
    # Show next 4 results in compact format
    if len(all_chunks) > 1:
        console.print()
        console.print(f"[{ACCENT_STYLE}]Other Matches[/{ACCENT_STYLE}]")
        console.print()
        
        for chunk_info in all_chunks[1:5]:  # Show up to 4 more
            _show_compact_match(chunk_info)
    
    # Summary
    console.print()
    summary = create_summary(
        "Found",
        f"{len(all_chunks)} matching chunks across {total_docs} documents"
    )
    console.print(summary)
    console.print()


def _show_top_result_card(chunk_info: Dict[str, Any]) -> None:
    """Show the top result chunk in a detail card with full excerpt."""
    collection = chunk_info["collection"]
    doc_id = chunk_info["doc_id"]
    chunk = chunk_info["chunk"]
    chunk_index = chunk_info["chunk_index"]
    
    # Build info rows
    rows = []
    
    # Collection and document
    rows.append(("Collection", collection))
    rows.append(("Document", doc_id))
    rows.append(("Part", f"Chunk {chunk_index}"))
    
    # Score
    score = chunk.get("score")
    if score is not None:
        score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
        rows.append(("Score", score_str))
    
    # Chunk ID if available
    chunk_id = chunk.get("id")
    if chunk_id:
        rows.append(("Match ID", chunk_id))
    
    # Extract content
    chunk_content_obj = chunk.get("content", {})
    if isinstance(chunk_content_obj, dict):
        chunk_content = chunk_content_obj.get("indexedData", "")
    else:
        chunk_content = str(chunk_content_obj)
    
    # Add content as a separate row with full text
    if chunk_content:
        # Show full content (or reasonable truncation)
        max_length = 500
        if len(chunk_content) > max_length:
            preview = chunk_content[:max_length] + "..."
        else:
            preview = chunk_content
        rows.append(("Excerpt", preview.strip()))
    
    # Create card using reusable component
    card = create_detail_card(
        title="Top Result",
        rows=rows,
    )
    console.print(card)


def _show_compact_match(chunk_info: Dict[str, Any]) -> None:
    """Show a compact single-line match."""
    collection = chunk_info["collection"]
    doc_id = chunk_info["doc_id"]
    chunk = chunk_info["chunk"]
    chunk_index = chunk_info["chunk_index"]
    chunk_id = chunk.get("id", "N/A")
    
    # Format: collection / document / part / match_id
    console.print(
        f"  • [{ACCENT_STYLE}]{collection}[/{ACCENT_STYLE}] / "
        f"{doc_id} / "
        f"[dim]Chunk {chunk_index}[/dim] / "
        f"[dim]{chunk_id}[/dim]"
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
        console.print(f"[{ACCENT_STYLE}]{collection_name}[/{ACCENT_STYLE}] [dim]({len(documents)} results)[/dim]")
        
        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            console.print(f"  {i}. {doc_id}")
        
        console.print()
    
    # Summary
    if total_results > 0:
        console.print(f"[{ACCENT_STYLE}]Total:[/{ACCENT_STYLE}] {total_results} results")
    else:
        console.print(f"[{SECONDARY_STYLE}]No results found[/{SECONDARY_STYLE}]")
    
    console.print()


def _show_collection_results(
    collection_name: str,
    documents: List[Dict[str, Any]],
    total_count: int,
    show_content: bool,
) -> None:
    """Show results for a single collection."""
    
    # Collection header
    if len(documents) < total_count:
        title_text = f"[bold]{collection_name}[/bold] [dim](showing {len(documents)} of {total_count})[/dim]"
    else:
        title_text = f"[bold]{collection_name}[/bold] [dim]({total_count} results)[/dim]"
    
    console.print(title_text)
    
    # Show each document as a card
    for i, doc in enumerate(documents):
        if i > 0:
            console.print()  # Space between results
        
        _show_document_card(doc, show_content)


def _show_document_card(doc: Dict[str, Any], show_content: bool) -> None:
    """Show a single document result as a card."""
    
    lines = []
    
    # Document ID/title
    doc_id = doc.get("id", "Unknown")
    lines.append(create_info_row("Document", doc_id))
    
    # Path/URL (if available)
    path = doc.get("path") or doc.get("url")
    if path:
        lines.append(create_info_row("Path", path))
    
    # Matched chunks with scores and content
    # Note: The key is camelCase from the search service
    matched_chunks = doc.get("matchedChunks", []) or doc.get("matched_chunks", [])
    if matched_chunks:
        lines.append(Text(""))  # Blank line
        lines.append(Text(f"Matched Chunks: {len(matched_chunks)}", style="dim"))
        
        if show_content:
            # Show top 3 chunks with content
            for i, chunk in enumerate(matched_chunks[:3], 1):
                lines.append(Text(""))  # Blank line
                
                # Chunk header with score
                chunk_header = f"Chunk {i}"
                score = chunk.get("score")
                if score is not None:
                    score_str = f" [{score:.4f}]" if isinstance(score, float) else f" [{score}]"
                    lines.append(Text(chunk_header + score_str, style="dim"))
                else:
                    lines.append(Text(chunk_header, style="dim"))
                
                # Chunk content (nested in 'content' -> 'indexedData')
                chunk_content_obj = chunk.get("content", {})
                if isinstance(chunk_content_obj, dict):
                    chunk_content = chunk_content_obj.get("indexedData", "")
                else:
                    chunk_content = str(chunk_content_obj)
                
                if chunk_content:
                    # Truncate if too long
                    max_length = 200
                    if len(chunk_content) > max_length:
                        preview = chunk_content[:max_length] + "..."
                    else:
                        preview = chunk_content
                    lines.append(Text(preview.strip()))
            
            # Show if there are more chunks
            if len(matched_chunks) > 3:
                lines.append(Text(""))  # Blank line
                lines.append(Text(f"... and {len(matched_chunks) - 3} more chunks", style="dim"))
    
    # Fallback to full content if no chunks available
    elif show_content:
        content = doc.get("content", "")
        if content:
            lines.append(Text(""))  # Blank line
            lines.append(Text("Content:", style="dim"))
            
            # Truncate to reasonable length
            max_length = 300
            if len(content) > max_length:
                preview = content[:max_length] + "..."
            else:
                preview = content
            
            lines.append(Text(preview.strip()))
    
    content = Group(*lines)
    
    # Create card
    panel = Panel(
        content,
        border_style=CARD_BORDER_STYLE,
        padding=CARD_PADDING,
    )
    
    console.print(panel)


def _show_error_result(collection_name: str, error: str) -> None:
    """Show error for a collection."""
    console.print(f"[red]{collection_name}:[/red] {error}")


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
    console.print()
    console.print(f"[{ACCENT_STYLE}]Search:[/{ACCENT_STYLE}] {query}")
    console.print()
    
    total_results = 0
    
    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            continue
        
        documents = collection_results.get("results", [])
        if not documents:
            continue
        
        total_results += len(documents)
        
        # Collection header
        console.print(f"[bold]{collection_name}[/bold] [dim]({len(documents)} results)[/dim]")
        
        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            score = doc.get("score")
            
            if score is not None:
                score_str = f" [{score:.4f}]" if isinstance(score, float) else f" [{score}]"
                console.print(f"  {i}. {doc_id}[dim]{score_str}[/dim]")
            else:
                console.print(f"  {i}. {doc_id}")
        
        console.print()
    
    # Summary
    if total_results > 0:
        console.print(f"[{ACCENT_STYLE}]Total:[/{ACCENT_STYLE}] {total_results} results")
    else:
        console.print(f"[{SECONDARY_STYLE}]No results found[/{SECONDARY_STYLE}]")
    
    console.print()
