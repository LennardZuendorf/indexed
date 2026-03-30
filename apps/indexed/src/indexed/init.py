"""`indexed init` — one-time setup command.

Downloads embedding models into the HuggingFace cache, creates the Indexed
data directory structure, and validates configuration.
Idempotent — safe to run multiple times.
"""

from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from indexed.utils.components import (
    create_detail_card,
    get_accent_style,
    get_dim_style,
    get_heading_style,
    get_success_style,
    print_success,
    print_warning,
)
from indexed.utils.console import console


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

    heading = get_heading_style()
    dim = get_dim_style()
    accent = get_accent_style()
    success = get_success_style()

    console.print()
    console.print(f"[{heading}]Indexed Setup[/{heading}]")
    console.print(f"[{dim}]Preparing your environment for semantic search.[/{dim}]")
    console.print()

    # Step 1: Data directories
    console.print(f"  [{accent}]1.[/{accent}] Creating data directories...", end=" ")
    from indexed_config import ensure_storage_dirs, get_global_root

    root = get_global_root()
    ensure_storage_dirs(root)
    console.print(f"[{success}]done[/{success}]")

    # Step 2: Config validation
    console.print(f"  [{accent}]2.[/{accent}] Validating configuration...", end=" ")
    try:
        from indexed_config import ConfigService

        ConfigService.instance()
        console.print(f"[{success}]done[/{success}]")
    except Exception as e:
        print_warning(str(e))

    # Step 3: Model
    if skip_model:
        console.print(
            f"  [{accent}]3.[/{accent}] Model download [{dim}]skipped[/{dim}]"
        )
    elif is_model_cached(model_name) and not force:
        console.print(
            f"  [{accent}]3.[/{accent}] Model [{accent}]{model_name}[/{accent}] "
            f"already in HuggingFace cache [{success}]done[/{success}]"
        )
    else:
        action = "Re-downloading" if force else "Downloading"
        console.print(
            f"  [{accent}]3.[/{accent}] {action} model [{accent}]{model_name}[/{accent}]..."
        )
        with Progress(
            SpinnerColumn(style=get_accent_style()),
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
        for m in info["models"]:
            card = create_detail_card(
                title=m["name"],
                rows=[
                    ("Size", f"{m['size_mb']} MB"),
                    ("Location", m["path"]),
                ],
            )
            console.print(card)
        console.print()

    print_success("Setup complete!")

    card = create_detail_card(
        title="Setup Summary",
        rows=[
            ("Cache", info["cache_dir"]),
            ("Models", f"{len(info['models'])} ({info['total_size_mb']} MB)"),
        ],
    )
    console.print(card)

    console.print()
    console.print(f"[{dim}]Next steps:[/{dim}]")
    console.print("  indexed index create files --collection my-docs")
    console.print('  indexed index search "your query"')
    console.print("  indexed mcp run")
