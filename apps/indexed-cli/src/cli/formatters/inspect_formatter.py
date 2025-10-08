"""Formatter for displaying CollectionInfo with Rich.

This module provides presentation-layer logic for formatting CollectionInfo
objects into beautiful Rich console output. It's completely independent of
the core data models and connection logic.
"""

import json
from typing import List, Optional
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from core.v1.engine.services import CollectionInfo
from cli.utils.console import console
from cli.components import (
    create_info_row,
    ACCENT_STYLE,
    CARD_BORDER_STYLE,
    CARD_PADDING,
    DETAIL_CARD_WIDTH,
)


def format_size(bytes: Optional[int]) -> str:
    """Format bytes to human-readable size."""
    if bytes is None:
        return "unknown"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_time(timestamp: Optional[str]) -> str:
    """Format timestamp to cleaner display."""
    if not timestamp:
        return "unknown"
    
    try:
        # Remove timezone and microseconds for cleaner display
        if "." in timestamp:
            timestamp = timestamp.split(".")[0]
        if "+" in timestamp:
            timestamp = timestamp.split("+")[0]
        return timestamp
    except:
        return timestamp


def format_collection_list(collections: List[CollectionInfo], verbose: bool = False) -> None:
    """Display a list of collections in table format.
    
    Args:
        collections: List of CollectionInfo objects to display
        verbose: If True, show detailed info for each collection
    """
    if not collections:
        console.print("\nNo collections found")
        console.print("\n[dim]Get started: indexed add[/dim]")
        return
    
    if verbose:
        _show_verbose_list(collections)
    else:
        _show_simple_list(collections)


def _show_simple_list(collections: List[CollectionInfo]) -> None:
    """Show simple collection list with unified panel design."""
    from rich.columns import Columns
    
    console.print()
    
    # Create panels for each collection
    panels = []
    total_docs = 0
    total_chunks = 0
    
    for coll in collections:
        total_docs += coll.number_of_documents
        total_chunks += coll.number_of_chunks
        
        # Create content using consistent info rows
        from rich.console import Group
        lines = [
            create_info_row("Docs", str(coll.number_of_documents)),
            create_info_row("Chunks", str(coll.number_of_chunks)),
        ]
        if coll.disk_size_bytes:
            lines.append(create_info_row("Size", format_size(coll.disk_size_bytes)))
        lines.append(create_info_row("Updated", format_time(coll.updated_time)))
        
        content = Group(*lines)
        
        # Create panel for collection
        panel = Panel(
            content,
            title=f"[bold]{coll.name}[/bold]",
            title_align="left",
            border_style=CARD_BORDER_STYLE,
            padding=CARD_PADDING,
        )
        panels.append(panel)
    
    # Display panels in columns (2 per row)
    if len(panels) > 0:
        console.print(Columns(panels, equal=True, expand=True))
    
    # Summary
    console.print()
    console.print(f"[{ACCENT_STYLE}]Total:[/{ACCENT_STYLE}] {total_docs} documents, {total_chunks} chunks")
    console.print()


def _show_verbose_list(collections: List[CollectionInfo]) -> None:
    """Show detailed collection info for all collections with unified design."""
    from rich.console import Group
    
    console.print()
    
    total_docs = 0
    total_chunks = 0
    
    for i, coll in enumerate(collections):
        if i > 0:
            console.print()  # Space between collections
        
        total_docs += coll.number_of_documents
        total_chunks += coll.number_of_chunks
        
        # Create content using consistent info rows
        lines = [
            create_info_row("Type", coll.source_type or "Unknown"),
        ]
        if coll.relative_path:
            lines.append(create_info_row("Path", coll.relative_path))
        lines.append(create_info_row("Documents", str(coll.number_of_documents)))
        lines.append(create_info_row("Chunks", str(coll.number_of_chunks)))
        if coll.disk_size_bytes:
            lines.append(create_info_row("Size", format_size(coll.disk_size_bytes)))
        lines.append(create_info_row("Updated", format_time(coll.updated_time)))
        
        content = Group(*lines)
        
        # Wrap in panel with consistent styling
        panel = Panel(
            content,
            title=f"[bold]{coll.name}[/bold]",
            title_align="left",
            border_style=CARD_BORDER_STYLE,
            padding=CARD_PADDING,
        )
        console.print(panel)
    
    # Summary
    console.print()
    console.print(f"[{ACCENT_STYLE}]Total:[/{ACCENT_STYLE}] {total_docs} documents, {total_chunks} chunks")
    console.print()


def format_collection_detail(info: CollectionInfo) -> None:
    """Display detailed information about a specific collection.
    
    Args:
        info: CollectionInfo object to display
    """
    console.print()
    
    # Build content using consistent info rows
    lines = []
    
    # Type info
    if info.source_type:
        lines.append(create_info_row("Type", info.source_type))
    
    # Path
    if info.relative_path:
        lines.append(create_info_row("Path", info.relative_path))
    
    # Core metrics
    lines.append(create_info_row("Docs", str(info.number_of_documents)))
    lines.append(create_info_row("Chunks", str(info.number_of_chunks)))
    
    # Storage info
    if info.disk_size_bytes:
        lines.append(create_info_row("Size", format_size(info.disk_size_bytes)))
    
    if info.index_size_bytes:
        lines.append(create_info_row("Index", format_size(info.index_size_bytes)))
    
    # Timestamps
    if info.created_time:
        lines.append(create_info_row("Created", format_time(info.created_time)))
    
    if info.updated_time:
        lines.append(create_info_row("Updated", format_time(info.updated_time)))
    
    # Computed statistics
    if info.avg_chunks_per_doc:
        lines.append(create_info_row("Avg/Doc", f"{info.avg_chunks_per_doc:.1f} chunks"))
    
    if info.avg_doc_size_bytes:
        lines.append(create_info_row("Avg Size", format_size(int(info.avg_doc_size_bytes))))
    
    # Join all lines
    from rich.console import Group
    content = Group(*lines)
    
    # Display in compact panel (left-aligned, not full width)
    panel = Panel(
        content,
        title=f"[bold]{info.name}[/bold]",
        title_align="left",
        border_style=CARD_BORDER_STYLE,
        padding=CARD_PADDING,
        width=DETAIL_CARD_WIDTH,
    )
    
    console.print(panel)
    console.print()


def format_collection_json(info: CollectionInfo) -> None:
    """Display collection info as JSON.
    
    Args:
        info: CollectionInfo object to display
    """
    output = {
        "name": info.name,
        "source_type": info.source_type,
        "path": info.relative_path,
        "documents": info.number_of_documents,
        "chunks": info.number_of_chunks,
        "disk_size_bytes": info.disk_size_bytes,
        "disk_size_human": format_size(info.disk_size_bytes),
        "updated": info.updated_time,
    }
    
    # Optional fields
    if info.index_size_bytes:
        output["index_size_bytes"] = info.index_size_bytes
        output["index_size_human"] = format_size(info.index_size_bytes)
    
    if info.created_time:
        output["created"] = info.created_time
    
    if info.avg_chunks_per_doc:
        output["avg_chunks_per_doc"] = round(info.avg_chunks_per_doc, 2)
    
    if info.avg_doc_size_bytes:
        output["avg_doc_size_bytes"] = round(info.avg_doc_size_bytes, 2)
        output["avg_doc_size_human"] = format_size(int(info.avg_doc_size_bytes))
    
    console.print(json.dumps(output, indent=2))


def format_collections_json(collections: List[CollectionInfo]) -> None:
    """Display list of collections as JSON.
    
    Args:
        collections: List of CollectionInfo objects to display
    """
    output = []
    for info in collections:
        item = {
            "name": info.name,
            "documents": info.number_of_documents,
            "chunks": info.number_of_chunks,
            "updated": info.updated_time,
            "source_type": info.source_type,
            "path": info.relative_path,
        }
        if info.disk_size_bytes:
            item["disk_size_bytes"] = info.disk_size_bytes
        output.append(item)
    
    console.print(json.dumps(output, indent=2))
