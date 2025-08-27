"""Register the 'delete' command on a Typer app."""

from typing import Optional
import typer


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
            False, "--yes", "-y", is_flag=True, help="Skip confirmation prompts"
        ),
    ) -> None:
        """Delete collections and all their data permanently with per-collection confirmation."""
        import cli.app as root
        
        try:
            # Resolve target collections
            statuses = root.svc_status([collection]) if collection else root.svc_status(None)
            if not statuses:
                if collection:
                    typer.echo(f"\n📂 Collection '{collection}' was not found. Nothing to delete.\n")
                    raise typer.Exit()
                else:
                    typer.echo("\n📂 No collections found. Nothing to delete.\n")
                    raise typer.Exit(0)

            # Nicely formatted list of candidate collections
            count = len(statuses)
            heading = (
                f"\n🗑️  Deletion candidates (1 collection):\n" if count == 1 else f"\n🗑️  Deletion candidates ({count} collections):\n"
            )
            typer.echo(heading)

            header = (
                f"{'Name':<32} │ {'Type':<16} │ {'Docs':>8} │ {'Chunks':>8} │ {'Updated':<22} │ Path"
            )
            typer.echo(header)
            typer.echo(
                "─" * 32
                + "─┼─"
                + "─" * 16
                + "─┼─"
                + "─" * 8
                + "─┼─"
                + "─" * 8
                + "─┼─"
                + "─" * 22
                + "─┼─"
                + "─" * 20
            )

            for s in statuses:
                name = s.name[:31]
                stype = (s.source_type or "-")[:15]
                docs = s.number_of_documents
                chunks = s.number_of_chunks
                updated = (s.updated_time or "-")[:21]
                path = s.relative_path or "-"
                typer.echo(
                    f"{name:<32} │ {stype:<16} │ {docs:>8d} │ {chunks:>8d} │ {updated:<22} │ {path}"
                )

            # Selection/confirmation phase
            names_to_delete = [s.name for s in statuses]

            if yes:
                typer.echo("\n⚠️  Proceeding to delete without confirmation (--yes).\n")
            else:
                confirmed_names: list[str] = []
                typer.echo("\nConfirm deletions one by one:\n")
                for s in statuses:
                    prompt = (
                        f"Delete collection '{s.name}'? This cannot be undone.\n"
                    )
                    if typer.confirm(prompt, default=False):
                        confirmed_names.append(s.name)
                names_to_delete = confirmed_names

            if not names_to_delete:
                typer.echo("\n✓ No collections selected. Deletion cancelled.\n")
                raise typer.Exit(0)

            root.svc_clear(names_to_delete)

            # Post-action summary
            listed = ", ".join(names_to_delete)
            typer.echo(f"\n✓ Deleted {len(names_to_delete)} collection(s): {listed}\n")

        finally:
            raise typer.Exit()