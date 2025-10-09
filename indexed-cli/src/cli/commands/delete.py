"""Delete command for removing collections."""

import typer
from core.v1 import Index

app = typer.Typer(help="Delete collections")


@app.command()
def delete(
    collection: str = typer.Argument(..., help="Collection name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove a collection from the index."""
    index = Index()
    
    if not force:
        confirm = typer.confirm(f"Delete collection '{collection}'?")
        if not confirm:
            typer.echo("Cancelled")
            raise typer.Exit(0)
    
    typer.echo(f"Deleting collection '{collection}'...")
    index.delete_collection(collection)
    typer.echo(f"✓ Collection '{collection}' deleted")
