"""`indexed init` — one-time setup command.

Downloads embedding models into the HuggingFace cache, creates the Indexed
data directory structure, and validates configuration.
Idempotent — safe to run multiple times.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


def init(
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Embedding model to download (default: all-MiniLM-L6-v2).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-download even if model is already cached.",
    ),
    skip_model: bool = typer.Option(
        False,
        "--skip-model",
        help="Skip model download (only create directories and validate config).",
    ),
) -> None:
    """Initialize Indexed: download models, create directories, validate config.

    Run this once after installation to set everything up.
    Safe to run again to verify or repair your setup.

    \b
    Examples:
        indexed init                              # Standard setup
        indexed init --model all-mpnet-base-v2    # Use a different model
        indexed init --force                      # Re-download model
        indexed init --skip-model                 # Directories only
    """
    from core.v1.engine.indexes.embeddings.model_manager import (
        DEFAULT_MODEL,
        ensure_model,
        get_cache_info,
        is_model_cached,
    )

    model_name = model or DEFAULT_MODEL

    console.print()
    console.print(
        Panel.fit(
            "[bold]Indexed Setup[/bold]\n"
            "Preparing your environment for semantic search.",
            border_style="bright_cyan",
        )
    )
    console.print()

    # Step 1: Data directories
    console.print("[bold]1.[/bold] Creating data directories...", end=" ")
    from indexed_config import ensure_storage_dirs, get_global_root

    root = get_global_root()
    ensure_storage_dirs(root)
    console.print("[green]done[/green]")

    # Step 2: Config validation
    console.print("[bold]2.[/bold] Validating configuration...", end=" ")
    try:
        from indexed_config import ConfigService

        ConfigService.instance()
        console.print("[green]done[/green]")
    except Exception as e:
        console.print(f"[yellow]warning: {e}[/yellow]")

    # Step 3: Model
    if skip_model:
        console.print("[bold]3.[/bold] Model download [dim]skipped[/dim]")
    elif is_model_cached(model_name) and not force:
        console.print(
            f"[bold]3.[/bold] Model [cyan]{model_name}[/cyan] "
            f"already in HuggingFace cache [green]done[/green]"
        )
    else:
        action = "Re-downloading" if force else "Downloading"
        console.print(f"[bold]3.[/bold] {action} model [cyan]{model_name}[/cyan]...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Downloading {model_name}...", total=None)
            ensure_model(model_name, force=force)
            progress.update(task, description="Cached")

    # Step 4: Summary
    console.print()
    info = get_cache_info()

    if info["models"]:
        table = Table(title="Cached Embedding Models", show_lines=False, padding=(0, 1))
        table.add_column("Model", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Location", style="dim", max_width=50)
        for m in info["models"]:
            table.add_row(m["name"], f"{m['size_mb']} MB", m["path"])
        console.print(table)
        console.print()

    console.print(
        Panel.fit(
            f"[green bold]Setup complete![/green bold]\n\n"
            f"HuggingFace cache: [dim]{info['cache_dir']}[/dim]\n"
            f"Models cached: {len(info['models'])} ({info['total_size_mb']} MB)\n\n"
            f"[dim]Next steps:[/dim]\n"
            f"  indexed index create files --collection my-docs\n"
            f'  indexed index search "your query"\n'
            f"  indexed mcp run",
            border_style="green",
        )
    )
