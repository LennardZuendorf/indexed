"""``indexed storage migrate`` — move local collections into the shared store.

Thin command: parse options, resolve the workspace, delegate to the migration
service, render the report. It imports no engine internals — the service talks
to the facade.
"""

from pathlib import Path
from typing import Optional

import typer

from ...utils.console import console
from ...utils.components import (
    create_detail_card,
    get_heading_style,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from ...utils.logging import setup_root_logger
from ...utils.simple_output import is_simple_output, print_json

app = typer.Typer(help="Move local collections into the shared global store")


@app.command()
def migrate(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report what would move, including collisions; change nothing",
    ),
    rollback: bool = typer.Option(
        False,
        "--rollback",
        help="Undo this workspace's migration and restore its local collections",
    ),
    on_collision: str = typer.Option(
        "abort",
        "--on-collision",
        help="What to do when the shared store already has a collection with the "
        "same name: abort (default), adopt (identical copy), or rename",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose (INFO) logging"
    ),
    log_level: Optional[str] = typer.Option(
        None, "--log-level", help="Set logging level (DEBUG, INFO, WARNING, ERROR)"
    ),
):
    """Share one index between projects instead of copying it.

    ``migrate`` moves this project's collections into ``~/.indexed`` under a
    stable id and records that id in a committed ``indexed.toml`` at the Git
    worktree root, so a second clone or project selects the same data instead of
    building a copy. ``--dry-run`` reports collisions and affected data; an
    interrupted run resumes where it stopped; ``--rollback`` puts everything
    back.

    Examples:
        indexed storage migrate --dry-run
        indexed storage migrate
        indexed storage migrate --rollback
    """
    from . import _migration as service

    if dry_run and rollback:
        print_error("Pass either --dry-run or --rollback, not both.")
        raise typer.Exit(1)

    setup_root_logger(level_str=log_level or ("INFO" if verbose else None))
    simple = is_simple_output()
    workspace = Path.cwd()

    try:
        if rollback:
            report = service.rollback(workspace)
        else:
            report = service.migrate(
                workspace, dry_run=dry_run, on_collision=on_collision
            )
    except Exception as exc:  # typed StorageError subclasses carry the remedy
        if simple:
            print_json({"status": "error", "error": str(exc)})
            raise typer.Exit(1)
        print_error(str(exc))
        raise typer.Exit(1)

    if simple:
        print_json(report.to_dict())
        return
    _render(report, workspace)


def _render(report, workspace: Path) -> None:
    """Render a MigrationReport as a Rich card."""
    console.print()
    if report.action == "noop":
        print_info("Nothing to migrate: this workspace has no local collections.")
        return
    if report.action == "plan":
        heading = "Shared store preview"
    elif report.action == "rollback":
        heading = "Rolled back the shared-store migration"
    else:
        heading = "Moved collections into the shared store"
    console.print(f"[{get_heading_style()}]{heading}:[/{get_heading_style()}]")
    console.print()

    for item in report.collections:
        rows = [
            ("Engine", f"v{item.engine}"),
            ("From", item.source),
            ("To", item.target),
            ("Data", f"{item.size_bytes / 1024:.1f} KiB"),
        ]
        console.print(create_detail_card(title=item.name, rows=rows))
        if item.collision:
            print_warning(f"{item.name}: {item.collision}")

    console.print()
    if report.collisions:
        print_warning(
            f"{report.collisions} collision(s). Nothing was changed. Re-run with "
            "--on-collision adopt (byte-identical copy) or rename."
        )
        return
    if report.action == "plan":
        print_info(
            f"Dry run: {len(report.collections)} collection(s), "
            f"{report.affected_bytes / 1024:.1f} KiB would move. Nothing changed."
        )
        return
    for message in report.messages:
        print_info(message)
    if report.resumed:
        print_info("Resumed an interrupted migration; no data was duplicated.")
    print_success(
        f"{len(report.collections)} collection(s) now live in the shared store; "
        f"this workspace points at {report.global_collections}."
        if report.action == "migrate"
        else f"{len(report.collections)} collection(s) restored to "
        f"{report.local_collections}."
    )
