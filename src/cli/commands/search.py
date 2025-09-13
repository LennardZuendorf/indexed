"""Register the 'search' command on a Typer app."""

from typing import Optional
import json
import typer

from main.services import SourceConfig

# --- simple styling helpers (ANSI) ---
RESET = "\033[0m"
BOLD = "\033[1m"

def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def register(app: typer.Typer) -> None:
    @app.command("search")
    def search_cmd(
        query: str = typer.Argument(..., help="Search query text", show_default=False),
        collection: Optional[str] = typer.Option(
            None,
            "--collection",
            "-c",
            help="Collection name to search (omit to search all collections)",
        ),
        index_name: str = typer.Option(
            None, "--index-name", help="Vector indexer configuration to use"
        ),
        max_chunks: Optional[int] = typer.Option(
            None, "--maxNumberOfChunks", help="Maximum number of text chunks to return"
        ),
        max_docs: Optional[int] = typer.Option(
            10, "--maxNumberOfDocuments", help="Maximum number of documents to return"
        ),
        include_full_text: bool = typer.Option(
            False,
            "--includeFullText",
            help="Include complete document text in results",
        ),
        include_all_chunks: bool = typer.Option(
            False,
            "--includeAllChunksText",
            help="Include all document chunks in results",
        ),
        include_matched_chunks: bool = typer.Option(
            False,
            "--includeMatchedChunksText",
            help="Include only matching chunks in results",
        ),
        json_out: bool = typer.Option(
            False, "--json", help="Output results in JSON format"
        ),
    ) -> None:
        """Search collections using semantic similarity.
        
        Performs semantic search across one or more collections using vector similarity.
        Results are ranked by relevance and can include document metadata, full text,
        and matching text chunks based on the specified options.
        
        Examples:
            Search all collections:
            $ indexed-cli search "microservices architecture"
            
            Search specific collection:
            $ indexed-cli search "kubernetes deployment" -c wiki
            
            Get JSON output with full text:
            $ indexed-cli search "API documentation" --json --includeFullText
            
            Limit results and include matching chunks:
            $ indexed-cli search "authentication" --maxNumberOfDocuments 5 --includeMatchedChunksText
        """
        import cli.app as root

        try:
            # Determine search scope
            if collection is None:
                cfgs = None
                scope_msg = "all collections"
            else:
                cfgs = [
                    SourceConfig(
                        name=collection,
                        type="localFiles",
                        base_url_or_path="",
                        indexer=index_name or root.DEFAULT_INDEXER,
                    )
                ]
                scope_msg = f"collection '{collection}'"

            # Display search info (unless JSON output requested)
            if not json_out:
                typer.echo(f"\n🔍  {bold('Searching')} {scope_msg} for: '{query}'")
                if max_docs != 10:
                    typer.echo(f"   Max documents: {max_docs}")
                if max_chunks:
                    typer.echo(f"   Max chunks: {max_chunks}")
                if index_name:
                    typer.echo(f"   Indexer: {index_name}")
                typer.echo()

            # Perform search
            result = root.svc_search(
                query,
                configs=cfgs,
                max_chunks=max_chunks,
                max_docs=max_docs,
                include_full_text=include_full_text,
                include_all_chunks=include_all_chunks,
                include_matched_chunks=include_matched_chunks,
            )

            # Output results
            if json_out:
                output = json.dumps(result, indent=2, ensure_ascii=False)
                typer.echo(output)
            else:
                # Format results nicely for human consumption
                if not result:
                    typer.echo("📭  No results found.\n")
                    raise typer.Exit(0)

                total_docs = sum(
                    len(v.get("results", [])) for v in result.values() if isinstance(v, dict)
                )
                collection_count = len(result)
                
                header = (
                    f"📄  {bold('Results')}: {total_docs} document(s)"
                    + (f" across {collection_count} collections" if collection_count > 1 else " in 1 collection")
                )
                typer.echo(header + ":\n")

                for collection_name, search_result in result.items():
                    if collection_count > 1:
                        typer.echo(f"{bold('Collection')}: {collection_name}")
                        typer.echo("─" * (len(collection_name) + 12))
                    
                    documents = search_result.get("results", []) if isinstance(search_result, dict) else []
                    for i, doc in enumerate(documents, 1):
                        title = doc.get('url') or doc.get('path') or str(doc.get('id', 'Document'))
                        # Derive a document-level score from the best matched chunk (if present)
                        score = 0.0
                        try:
                            score = max((mc.get('score', 0.0) for mc in doc.get('matchedChunks', [])), default=0.0)
                        except Exception:
                            score = 0.0
                        typer.echo(f"{i:2d}. {title}  (score: {score:.3f})")
                        
                        if doc.get('summary'):
                            typer.echo(f"    {doc['summary']}")
                        
                        if include_matched_chunks and doc.get('matchedChunks'):
                            typer.echo("    Matched chunks:")
                            for chunk in doc['matchedChunks'][:3]:  # Show first 3 chunks
                                content = chunk.get('content')
                                if content is not None:
                                    preview = content[:100] + "..." if len(content) > 100 else content
                                else:
                                    preview = f"(chunk {chunk.get('chunkNumber')})"
                                typer.echo(f"    • {preview}")
                        
                        typer.echo()
                    
                    if collection_count > 1:
                        typer.echo()

        except (SystemExit, typer.Exit):
            # Re-raise Typer's normal exit without treating as error
            raise
        except Exception as exc:  # pragma: no cover - error paths
            if json_out:
                error_result = {"error": str(exc)}
                typer.echo(json.dumps(error_result, indent=2), err=True)
            else:
                typer.echo(f"\n❌  Search error: {exc}\n", err=True)
            raise typer.Exit(1)
