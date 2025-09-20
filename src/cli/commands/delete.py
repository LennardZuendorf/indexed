"""Register the 'delete' command on a Typer app."""

from typing import Optional
import typer

from cli.formatters.delete_formatter import render_delete_candidates, show_delete_result


def register(app: typer.Typer) -> None:
    @app.command("delete")
    def delete_cmd(
        collection: Optional[str] = typer.Option(
            None,
            "--collection",
            "-c",
            help="Collection name to delete (omit to select from all collections)",
        ),
        yes: bool = typer.Option(
            False, "--yes", "-y", help="Skip confirmation prompts"
        ),
    ) -> None:
        """Delete collections and all their data permanently with per-collection confirmation."""
        import cli.app as root
        
        try:
            # Resolve target collections
            statuses = root.svc_status([collection]) if collection else root.svc_status(None)
            if not statuses:
                if collection:
                    typer.echo(f"📂 Collection '{collection}' was not found. Nothing to delete.")
                    raise typer.Exit()
                else:
                    typer.echo("📂 No collections found. Nothing to delete.")
                    raise typer.Exit(0)

            # Show candidates table
            render_delete_candidates(statuses)

            # Selection/confirmation phase
            names_to_delete = [s.name for s in statuses]

            if yes:
                typer.echo("⚠️  Proceeding to delete without confirmation (--yes).")
            else:
                confirmed_names: list[str] = []
                typer.echo("Confirm deletions one by one:")
                for s in statuses:
                    prompt = f"Delete collection '{s.name}'? This cannot be undone."
                    if typer.confirm(prompt, default=False):
                        confirmed_names.append(s.name)
                names_to_delete = confirmed_names

            if not names_to_delete:
                show_delete_result([])
                raise typer.Exit(0)

            root.svc_clear(names_to_delete)
            show_delete_result(names_to_delete)

        finally:
            raise typer.Exit()