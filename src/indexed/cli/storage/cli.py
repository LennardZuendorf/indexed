"""``indexed storage`` command group.

One subcommand today (``migrate``): move this workspace's collections into the
shared global store, and roll it back. Assembly point only — see
``commands/migrate.py`` and ``commands/_migration.py``.
"""

import typer

from .commands.migrate import migrate

app = typer.Typer(help="Manage the shared collection store")

app.command(
    "migrate",
    help="Move local collections into the shared global store (or roll it back)",
)(migrate)

__all__ = ["app", "migrate"]
