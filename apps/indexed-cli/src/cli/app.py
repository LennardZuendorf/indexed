"""Indexed CLI application.

Provides legacy proxies and stateless commands backed by services.
"""

import json
import os
import typer
from typing import Optional
from utils.logger import setup_root_logger

# Re-export service interfaces for tests and command modules to reference dynamically
from core.v1.engine.services import (
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
from .commands.legacy.legacy import legacy_app  # noqa: E402

app.add_typer(legacy_app, name="legacy")

# Register new commands using plugin architecture
from .commands import create, search, update, delete, config  # noqa: E402
from .commands.inspect import inspect_collections  # noqa: E402

app.add_typer(create.app, name="create")
app.add_typer(config.app, name="config")
app.command("search")(search.search)
app.command("update")(update.update)
app.command("delete")(delete.delete)
app.command("inspect")(inspect_collections)



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
