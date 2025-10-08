"""Inspect command for viewing collection details."""

import typer
from core.v1 import Index

app = typer.Typer(help="Inspect collections")


@app.command()
def inspect(
    collection: str = typer.Argument(None, help="Collection name to inspect (optional)"),
):
    """View detailed information about collections.
    
    If no collection name is provided, shows all collections in a table.
    If a collection name is provided, shows detailed information for that collection.
    """
    index = Index()
    
    if collection:
        # Show detailed info for specific collection
        status_list = index.status(collection)
        
        if not status_list:
            typer.echo(f"Error: Collection '{collection}' not found", err=True)
            raise typer.Exit(1)
        
        coll = status_list
        
        typer.echo(f"Collection: {coll.name}")
        typer.echo(f"Documents: {coll.number_of_documents}")
        typer.echo(f"Chunks: {coll.number_of_chunks}")
        typer.echo(f"Updated: {coll.updated_time}")
        typer.echo(f"Last Modified: {coll.last_modified_document_time}")
        typer.echo(f"Indexers: {', '.join(coll.indexers)}")
        
        if coll.source_type:
            typer.echo(f"Source Type: {coll.source_type}")
        if coll.relative_path:
            typer.echo(f"Path: {coll.relative_path}")
        if coll.disk_size_bytes:
            typer.echo(f"Size: {_human_size(coll.disk_size_bytes)}")
    else:
        # Show table of all collections
        status_list = index.status()
        
        if not status_list:
            typer.echo("No collections found")
            return
        
        typer.echo(f"\nFound {len(status_list)} collection(s):\n")
        
        # Header
        typer.echo(f"{'Name':<30} {'Docs':>8} {'Chunks':>8} {'Updated':<22}")
        typer.echo("─" * 70)
        
        # Rows
        for coll in status_list:
            name = coll.name[:29] if len(coll.name) > 29 else coll.name
            updated = coll.updated_time[:21] if coll.updated_time else "-"
            typer.echo(
                f"{name:<30} {coll.number_of_documents:>8} {coll.number_of_chunks:>8} {updated:<22}"
            )
        
        typer.echo()


def _human_size(n: int) -> str:
    """Convert bytes to human-readable size."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024.0:
            return f"{size:.1f}{u}"
        size /= 1024.0
    return f"{size:.1f}PB"
