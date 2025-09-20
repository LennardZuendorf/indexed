"""Register the 'search' command on a Typer app."""

from typing import Optional
import json
import typer

from main.services import resolve_and_extract, ConfigSlice, SearchResult
from cli.utils.output_mode import should_output_json
from cli.formatters.search_formatter import render_search_results


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
            False, "--json", "--json-output", help="Output results in JSON format"
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
            # Determine output mode
            use_json = should_output_json("cli", json_out)
            
            # Build overrides and resolve config slice
            overrides = {
                "collection": collection,
                "index_name": index_name,
                "max_chunks": max_chunks,
                "max_docs": max_docs,
                "include_full_text": include_full_text,
                "include_all_chunks": include_all_chunks,
                "include_matched_chunks": include_matched_chunks,
            }
            _settings, args = resolve_and_extract(
                ConfigSlice.SEARCH,
                profile=None,
                overrides=overrides,
            )

            # Perform search
            result = root.svc_search(
                query,
                configs=args.configs,
                max_chunks=args.max_chunks,
                max_docs=args.max_docs,
                include_full_text=args.include_full_text,
                include_all_chunks=args.include_all_chunks,
                include_matched_chunks=args.include_matched_chunks,
            )

            # Output results
            if use_json:
                output = json.dumps(result, indent=2, ensure_ascii=False)
                typer.echo(output)
            else:
                # Convert dict result to SearchResult objects for formatter
                search_results = []
                for collection_name, search_result in result.items():
                    if isinstance(search_result, dict):
                        documents = search_result.get("results", [])
                        for doc in documents:
                            # Extract best score from matched chunks
                            score = None
                            if doc.get('matchedChunks'):
                                try:
                                    score = max((mc.get('score', 0.0) for mc in doc['matchedChunks']), default=0.0)
                                except Exception:
                                    score = 0.0
                            
                            search_results.append(SearchResult(
                                id=doc.get('id', ''),
                                collection_name=collection_name,
                                url=doc.get('url'),
                                path=doc.get('path'),
                                score=score,
                                matched_chunks=doc.get('matchedChunks', [])
                            ))
                
                render_search_results(search_results, include_chunks=include_matched_chunks)

        except (SystemExit, typer.Exit):
            # Re-raise Typer's normal exit without treating as error
            raise
        except Exception as exc:  # pragma: no cover - error paths
            # Fallback to flag value if output mode helper fails
            output_json = json_out
            try:
                output_json = should_output_json("cli", json_out)
            except Exception:
                pass
            
            if output_json:
                error_result = {"error": str(exc)}
                typer.echo(json.dumps(error_result, indent=2), err=True)
            else:
                typer.echo(f"\n❌  Search error: {exc}\n", err=True)
            raise typer.Exit(1)
