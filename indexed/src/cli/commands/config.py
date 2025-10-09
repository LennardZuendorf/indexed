"""Config command for managing index configuration."""

import typer
from core.v1 import Config

app = typer.Typer(help="Manage configuration")


@app.command("show")
def show():
    """Display current configuration."""
    config = Config.load()
    typer.echo(config.pretty_print())


@app.command("init")
def init(
    embedding_model: str = typer.Option(None, "--model", "-m", help="Embedding model"),
    chunk_size: int = typer.Option(None, "--chunk-size", help="Chunk size"),
    storage_path: str = typer.Option(None, "--storage", "-s", help="Storage path"),
):
    """Initialize a new configuration."""
    kwargs = {}
    if embedding_model:
        kwargs["embedding_model"] = embedding_model
    if chunk_size:
        kwargs["chunk_size"] = chunk_size
    if storage_path:
        kwargs["storage_path"] = storage_path
    
    config = Config(**kwargs)
    config.save()
    typer.echo("✓ Configuration initialized")
    typer.echo("\n" + config.pretty_print())
