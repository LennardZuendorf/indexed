"""Register the 'update' command on a Typer app."""

from typing import Optional
import typer

from main.services import SourceConfig

# --- simple styling helpers (ANSI) ---
RESET = "\033[0m"
BOLD = "\033[1m"

def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def register(app: typer.Typer) -> None:
    @app.command("update")
    def update_cmd(
        collection: Optional[str] = typer.Option(
            None,
            "--collection",
            "-c",
            help="Collection name to update (omit to update all collections)",
        ),
    ) -> None:
        """Update existing collections with latest data from their sources."""
        import cli.app as root

        try:
            if collection is None:
                names = [s.name for s in root.svc_status(None)]
                scope_msg = "all collections"
            else:
                names = [collection]
                scope_msg = f"collection '{collection}'"
            if not names:
                typer.echo("📦  No collections found to update\n")
                raise typer.Exit(0)

            typer.echo(f"\n♻️  {bold('Updating')} {scope_msg}…\n")
            cfgs = [
                SourceConfig(
                    name=n,
                    type="localFiles",
                    base_url_or_path="",
                    indexer=root.DEFAULT_INDEXER,
                )
                for n in names
            ]
            root.svc_update(cfgs)
            typer.echo(f"✅  {bold('Updated')} {len(names)} collection(s)\n")
        except Exception as exc:  # pragma: no cover - error paths
            typer.echo(f"✗  Error updating collections: {exc}\n", err=True)
            raise typer.Exit(1)
