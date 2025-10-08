"""Update command for refreshing collections."""

import typer
from core.v1 import Index

app = typer.Typer(help="Update collections")


@app.command()
def update(
    collection: str = typer.Argument(..., help="Collection name to update"),
):
    """Refresh and re-index a collection."""
    index = Index()
    
    typer.echo(f"Updating collection '{collection}'...")
    index.update_collection(collection)
    typer.echo(f"✓ Collection '{collection}' updated")
