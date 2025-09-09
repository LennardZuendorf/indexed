"""Register the 'update' command on a Typer app."""

from typing import Optional
import typer

from main.services import SourceConfig


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
            else:
                names = [collection]
            if not names:
                typer.echo("No collections found to update")
                raise typer.Exit(0)
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
            typer.echo(f"✓ Updated {len(names)} collection(s)")
        except Exception as exc:  # pragma: no cover - error paths
            typer.echo(f"✗ Error updating collections: {exc}", err=True)
            raise typer.Exit(1)
