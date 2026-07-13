"""`indexed init` — one-time setup command.

Downloads embedding models into the HuggingFace cache, creates the Indexed
data directory structure, and validates configuration.
Idempotent — safe to run multiple times.
"""

from typing import Optional

import typer
from rich.text import Text

from indexed.cli.utils.components import (
    get_dim_style,
    get_heading_style,
    get_label_style,
    print_success,
    print_warning,
)
from indexed.cli.utils.console import console, render_user_text
from indexed.cli.utils.progress_bar import create_phased_progress
from indexed.cli.utils.storage_info import display_storage_mode_for_command


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
    from indexed.core.v1.engine.indexes.embeddings.model_manager import (
        DEFAULT_MODEL,
        ensure_model,
        get_cache_info,
        is_model_cached,
    )
    from indexed.config import get_config, ensure_storage_dirs, get_global_root

    model_name = model or DEFAULT_MODEL

    # Initialize ConfigService and display storage mode
    get_config()
    display_storage_mode_for_command(console)

    heading = get_heading_style()
    dim = get_dim_style()
    title = f"[{heading}]Initializing Indexed[/{heading}]"

    root = get_global_root()

    with create_phased_progress(title=title, show_bar=False) as progress:
        # Phase 1: Create data directories
        progress.start_phase("Creating data directories")
        ensure_storage_dirs(root)
        progress.finish_phase("Creating data directories")

        # Phase 2: Validate configuration
        progress.start_phase("Validating configuration")
        try:
            get_config()
        except Exception as e:
            print_warning(str(e))
        progress.finish_phase("Validating configuration")

        # Phase 3: Embedding model
        if skip_model:
            progress.start_phase("Download embedding model")
            progress.log("skipped (--skip-model)")
            progress.finish_phase("Download embedding model")
        elif is_model_cached(model_name) and not force:
            progress.start_phase("Download embedding model")
            progress.log(f"{model_name} already cached")
            progress.finish_phase("Download embedding model")
        else:
            action = "Re-downloading" if force else "Downloading"
            phase_name = f"{action} model {model_name}"
            progress.start_phase(phase_name)
            ensure_model(model_name, force=force)
            progress.finish_phase(phase_name)

    # Summary
    info = get_cache_info()
    label = get_label_style()

    console.print()
    print_success("Setup complete!")
    console.print()

    # Model name / cache dir are content-derived (HF model id, filesystem
    # path) — rendered as literal Text, never markup-parsed. The surrounding
    # label/dim styling is the app's own intentional markup and stays as-is.
    if info["models"]:
        for m in info["models"]:
            console.print(
                Text.assemble(
                    Text.from_markup(f"  [{label}]{'Model':<10}[/{label}]"),
                    render_user_text(m["name"]),
                    Text.from_markup(f"  [{dim}]{m['size_mb']} MB[/{dim}]"),
                )
            )
    console.print(
        Text.assemble(
            Text.from_markup(f"  [{label}]{'Cache':<10}[/{label}]"),
            render_user_text(info["cache_dir"], style=dim),
        )
    )

    console.print()
    console.print(f"[{dim}]Next steps:[/{dim}]")
    console.print("  indexed index create files --collection my-docs")
    console.print('  indexed index search "your query"')
    console.print("  indexed mcp run")
