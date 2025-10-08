"""Search command for querying collections."""

import typer
from core.v1 import Index

app = typer.Typer(help="Search collections")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option(None, "--collection", "-c", help="Collection name to search"),
    limit: int = typer.Option(5, "--limit", "-l", help="Number of results to display"),
):
    """Search across collections."""
    index = Index()
    
    typer.echo(f"Searching for: {query}")
    if collection:
        typer.echo(f"Collection: {collection}\n")
    
    results = index.search(query, collection=collection)
    
    for coll_name, coll_results in results.items():
        docs = coll_results.get("results", [])
        typer.echo(f"Collection: {coll_name}")
        typer.echo(f"Found {len(docs)} documents\n")
        
        for doc in docs[:limit]:
            typer.echo(f"  ID: {doc.get('id')}")
            typer.echo(f"  Score: {doc.get('score', 'N/A')}")
            content = doc.get('content', '')
            if content:
                preview = content[:200] + "..." if len(content) > 200 else content
                typer.echo(f"  Content: {preview}")
            typer.echo("")
