"""Register the 'update' command on a Typer app."""

from typing import Optional
import typer

from main.services import SourceConfig
from cli.formatters.update_formatter import show_update_start, update_collection, show_update_summary


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
                # Get all collections for update
                all_statuses = root.svc_status(None)
                names = [s.name for s in all_statuses]
            else:
                names = [collection]
                all_statuses = None
                
            if not names:
                typer.echo("📦 No collections found to update")
                raise typer.Exit(0)

            # Show initial message
            show_update_start(names)
            
            # Create configs for all collections
            cfgs = [
                SourceConfig(
                    name=n,
                    type="localFiles",
                    base_url_or_path="",
                    indexer=root.DEFAULT_INDEXER,
                )
                for n in names
            ]
            
            # Process all collections with spinner
            if len(names) == 1:
                with update_collection(names[0]):
                    root.svc_update(cfgs)
            else:
                # For multiple collections, show a general spinner
                with update_collection("multiple collections"):
                    root.svc_update(cfgs)
            
            # Get updated collection statuses for display
            # If we already have all statuses and updated all, get fresh status
            # If we updated specific collections, get status for those
            if collection is None and all_statuses:
                # We updated all collections, get fresh status for all
                updated_statuses = root.svc_status(None)
            else:
                # We updated specific collection(s), get status for those
                updated_statuses = root.svc_status(names)
            
            # Show final summary with current status
            show_update_summary(len(names), collection_statuses=updated_statuses)
                
        except Exception as exc:  # pragma: no cover - error paths
            typer.echo(f"❌ Error updating collections: {exc}", err=True)
            raise typer.Exit(1)
