"""Register the 'search' command on a Typer app."""

from typing import Optional
import json
import typer

from main.services import SourceConfig


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
            is_flag=True,
            help="Include complete document text in results",
        ),
        include_all_chunks: bool = typer.Option(
            False,
            "--includeAllChunksText",
            is_flag=True,
            help="Include all document chunks in results",
        ),
        include_matched_chunks: bool = typer.Option(
            False,
            "--includeMatchedChunksText",
            is_flag=True,
            help="Include only matching chunks in results",
        ),
        json_out: bool = typer.Option(
            False, "--json", is_flag=True, help="Output results in JSON format"
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
                typer.echo(f"\n🔍 Searching {scope_msg} for: '{query}'")
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
                    typer.echo("📭 No results found.\n")
                    raise typer.Exit(0)

                total_docs = sum(len(docs) for docs in result.values())
                collection_count = len(result)
                
                if collection_count == 1:
                    typer.echo(f"📄 Found {total_docs} document(s) in 1 collection:\n")
                else:
                    typer.echo(f"📄 Found {total_docs} document(s) across {collection_count} collections:\n")

                for collection_name, documents in result.items():
                    if collection_count > 1:
                        typer.echo(f"Collection: {collection_name}")
                        typer.echo("─" * (len(collection_name) + 12))
                    
                    for i, doc in enumerate(documents, 1):
                        title = doc.get('title', 'Untitled')
                        score = doc.get('score', 0.0)
                        typer.echo(f"{i:2d}. {title} (score: {score:.3f})")
                        
                        if doc.get('summary'):
                            typer.echo(f"    {doc['summary']}")
                        
                        if include_matched_chunks and doc.get('matched_chunks'):
                            typer.echo("    Matched chunks:")
                            for chunk in doc['matched_chunks'][:3]:  # Show first 3 chunks
                                preview = chunk[:100] + "..." if len(chunk) > 100 else chunk
                                typer.echo(f"    • {preview}")
                        
                        typer.echo()
                    
                    if collection_count > 1:
                        typer.echo()

        except Exception as exc:  # pragma: no cover - error paths
            if json_out:
                error_result = {"error": str(exc)}
                typer.echo(json.dumps(error_result, indent=2), err=True)
            else:
                typer.echo(f"\n❌ Search error: {exc}\n", err=True)
            raise typer.Exit(1)
