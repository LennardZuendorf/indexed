"""Indexed CLI application.

Provides legacy proxies and stateless commands backed by services.
"""

import json
import os
import typer
from typing import Optional
from main.utils.logger import setup_root_logger

# Re-export service interfaces for tests and command modules to reference dynamically
from main.services import (
    SourceConfig,
    clear as svc_clear,
    create as svc_create,
    search as svc_search,
    status as svc_status,
    update as svc_update,
)

# Main Typer application
app = typer.Typer(
    add_completion=False, help="Indexed CLI - Document indexing and search tool"
)
# Global logging init via callback (runs before subcommands)
@app.callback()
def _init_logging(
    verbose: bool = typer.Option(
        False, "--verbose", help="Enable verbose (DEBUG) logging"
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Logging level (overrides --verbose)",
        case_sensitive=False,
        show_choices=True,
        rich_help_panel="Logging",
    ),
    json_logs: bool = typer.Option(
        False, "--json-logs", help="Output logs as JSON (structured)"
    ),
) -> None:
    # Resolve effective level with precedence: CLI > env > config (handled later) > default
    env_level = os.getenv("INDEXED_LOG_LEVEL")
    level = (log_level or ("DEBUG" if verbose else None) or env_level or "INFO").upper()
    json_mode = json_logs or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    setup_root_logger(level_str=level, json_mode=json_mode)

# Shared default indexer constant (kept here for backward compatibility with tests)
DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

# Register legacy command group
from .commands.legacy import legacy_app  # noqa: E402

app.add_typer(legacy_app, name="legacy")

# Register create commands group
from .commands.create import create_app  # noqa: E402

app.add_typer(create_app, name="create")

# Register config commands group
from .commands.config import config_app  # noqa: E402

app.add_typer(config_app, name="config")

# Register other top-level commands (search/update)
from .commands.search import register as register_search  # noqa: E402
from .commands.update import register as register_update  # noqa: E402
from .commands.delete import register as register_delete  # noqa: E402

register_search(app)
register_update(app)
register_delete(app)

@app.command("inspect")
def inspect_cmd(
    json_output: bool = typer.Option(
        False, "--json", is_flag=True, help="Output as JSON instead of a table"
    ),
    include_index_size: bool = typer.Option(
        False,
        "--include-index-size",
        is_flag=True,
        help="Include on-disk index size in bytes (if available)",
    ),
) -> None:
    """Inspect available collections with metadata in a table or JSON."""
    try:
        statuses = svc_status(None, include_index_size=include_index_size)
        
        if json_output:
            # Convert to JSON-serializable structure
            out = []
            for s in statuses:
                out.append(
                    {
                        "name": s.name,
                        "number_of_documents": s.number_of_documents,
                        "number_of_chunks": s.number_of_chunks,
                        "updated_time": s.updated_time,
                        "last_modified_document_time": s.last_modified_document_time,
                        "indexers": s.indexers,
                        "index_size": s.index_size,
                        "source_type": s.source_type,
                        "relative_path": s.relative_path,
                        "disk_size_bytes": s.disk_size_bytes,
                    }
                )
            typer.echo(json.dumps(out))
            return
        
        # Initial response with collection count
        collection_count = len(statuses)
        if collection_count == 0:
            typer.echo("\n📂 No collections found\n")
            return
        elif collection_count == 1:
            typer.echo("\n📂 Found 1 collection:\n")
        else:
            typer.echo(f"\n📂 Found {collection_count} collections:\n")

        # Header with better spacing
        header = (
            f"{'Name':<32} │ {'Type':<16} │ {'Docs':>8} │ {'Chunks':>8} │ {'Updated':<22} │ {'Size':>12} │ Path"
        )
        typer.echo(header)
        typer.echo("─" * 32 + "─┼─" + "─" * 16 + "─┼─" + "─" * 8 + "─┼─" + "─" * 8 + "─┼─" + "─" * 22 + "─┼─" + "─" * 12 + "─┼─" + "─" * 20)

        def human_size(n: int | None) -> str:
            if not n:
                return "-"
            units = ["B", "KB", "MB", "GB", "TB"]
            size = float(n)
            for u in units:
                if size < 1024.0:
                    return f"{size:.1f}{u}"
                size /= 1024.0
            return f"{size:.1f}PB"

        for s in statuses:
            name = s.name[:31]  # Truncate if too long
            stype = (s.source_type or "-")[:15]
            docs = s.number_of_documents
            chunks = s.number_of_chunks
            updated = (s.updated_time or "-")[:21]
            size = human_size(s.disk_size_bytes)
            path = s.relative_path or "-"
            
            typer.echo(
                f"{name:<32} │ {stype:<16} │ {docs:>8d} │ {chunks:>8d} │ {updated:<22} │ {size:>12} │ {path}"
            )

            typer.echo("\n")

    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)


__all__ = [
    "app",
    "DEFAULT_INDEXER",
    # Re-exports used by tests for monkeypatching
    "svc_create",
    "svc_update",
    "svc_clear",
    "svc_search",
    "svc_status",
    "SourceConfig",
]


if __name__ == "__main__":
    app()
