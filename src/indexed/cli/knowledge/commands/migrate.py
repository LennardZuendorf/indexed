"""Migrate command: convert a v1 collection to the v2 engine (core-v2/4, R7).

Thin command — parse options, resolve storage, delegate to the facade-exposed
``migrate`` service, render the result. It imports ONLY ``indexed.core.engine``
(the version-dispatching facade) for engine work (above-facade rule); the actual
migration lives in ``indexed.core.v2.migration``. Heavy/core imports stay lazy
(``__getattr__``) so CLI startup stays <1s.
"""

from typing import Optional

import typer

from ...utils.console import console
from ...utils.components import (
    create_detail_card,
    create_summary,
    get_accent_style,
    get_heading_style,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from ...utils.logging import is_verbose_mode
from ...utils.simple_output import is_simple_output, print_json
from ...utils.storage_info import display_storage_mode_for_command

app = typer.Typer(help="Migrate a v1 collection to the v2 engine")


@app.command()
def migrate(
    ctx: typer.Context,
    collection: str = typer.Argument(..., help="Collection name to migrate to v2"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the migration (counts + target model/store); change nothing",
    ),
    from_source: bool = typer.Option(
        False,
        "--from-source",
        help="Re-read documents from the live source instead of stored content",
    ),
    purge_backup: bool = typer.Option(
        False,
        "--purge-backup",
        help="Remove the <name>.v1-backup directory after a successful migration",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose (INFO) logging",
        rich_help_panel="Logging",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON (structured)",
        rich_help_panel="Logging",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        rich_help_panel="Logging",
    ),
):
    """Convert a v1 collection to the v2 engine (offline by default).

    Builds the v2 collection aside, validates it (counts + a probe search), then
    swaps it in — keeping the original as ``<name>.v1-backup`` (rollback-safe).
    ``--dry-run`` previews without changing anything; ``--from-source`` re-reads
    the live source; ``--purge-backup`` cleans up the backup afterward.

    Examples:
        indexed index migrate my-docs --dry-run   # preview only
        indexed index migrate my-docs             # migrate, keep backup
        indexed index migrate my-docs --purge-backup
    """
    # Module-level lazy service (supports monkeypatching in tests).
    from . import migrate as this_module
    from indexed.cli.composition import (
        make_manifest_factory,
        resolve_collections_context,
    )

    setup_root_logger_svc = this_module.setup_root_logger

    mode_override = ctx.obj.get("mode_override") if ctx.obj else None
    cli_ctx = resolve_collections_context(mode_override=mode_override)
    collections_path = str(cli_ctx.collections_path)

    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger_svc(level_str=effective_level, json_mode=json_logs)

    simple = is_simple_output()
    if not is_verbose_mode() and not simple:
        display_storage_mode_for_command(console)

    # --from-source rebuilds the connector via the manifest (the from_manifest
    # seam update uses); the offline default needs no connector wiring.
    manifest_factory = make_manifest_factory(cli_ctx) if from_source else None

    try:
        result = this_module.svc_migrate(
            collection,
            collections_path=collections_path,
            dry_run=dry_run,
            from_source=from_source,
            purge_backup=purge_backup,
            manifest_factory=manifest_factory,
        )
    except Exception as e:
        if simple:
            print_json({"status": "error", "collection": collection, "error": str(e)})
            raise typer.Exit(1)
        print_error(f"Failed to migrate '{collection}': {e}")
        raise typer.Exit(1)

    _render_result(result, simple)


def _render_result(result, simple: bool) -> None:
    """Render a MigrationResult as ``--simple-output`` JSON or a Rich card."""
    if simple:
        print_json(
            {
                "status": result.action,
                "collection": result.name,
                "dry_run": result.dry_run,
                "from_source": result.from_source,
                "documents": result.number_of_documents,
                "chunks": result.number_of_chunks,
                "embedding_model": result.embedding_model,
                "vector_store": result.vector_store,
                "backup_path": result.backup_path,
                "backup_purged": result.backup_purged,
                "validated": result.validated,
            }
        )
        return

    if result.action == "purge-backup":
        console.print()
        print_success(f"Removed the v1 backup for '{result.name}'")
        return

    console.print()
    if result.dry_run:
        console.print(
            f"[{get_heading_style()}]Migration preview for "
            f"[{get_accent_style()}]{result.name}[/{get_accent_style()}] "
            f"(v1 -> v2):[/{get_heading_style()}]"
        )
    else:
        console.print(
            f"[{get_heading_style()}]Migrated "
            f"[{get_accent_style()}]{result.name}[/{get_accent_style()}] "
            f"to the v2 engine:[/{get_heading_style()}]"
        )
    console.print()

    rows = [
        ("Documents", str(result.number_of_documents)),
        ("Chunks", str(result.number_of_chunks)),
        ("Embedding model", result.embedding_model),
        ("Vector store", result.vector_store),
        ("Source", "live source" if result.from_source else "stored content"),
    ]
    console.print(create_detail_card(title=result.name, rows=rows))

    if result.dry_run:
        console.print()
        print_info("Dry run: no files were changed. Re-run without --dry-run.")
        return

    console.print()
    print_success(f"Collection '{result.name}' is now a v2 collection")
    if result.backup_purged:
        print_info("The v1 backup was removed (--purge-backup).")
    elif result.backup_path:
        print_warning(
            f"The original v1 collection is preserved at '{result.name}.v1-backup'. "
            f"Remove it with: indexed index migrate {result.name} --purge-backup"
        )
    console.print()
    console.print(create_summary("Migrated", f"{result.name} to v2."))


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance.

    The service resolves through the version-dispatching facade
    (``indexed.core.engine.migrate``) under a DISTINCT name (``svc_migrate``) so
    it doesn't collide with this module's ``migrate`` Typer command; tests
    monkeypatch ``migrate.svc_migrate``.
    """
    if name == "svc_migrate":
        from indexed.core.engine import migrate

        return migrate
    elif name == "setup_root_logger":
        from ...utils.logging import setup_root_logger

        return setup_root_logger
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
