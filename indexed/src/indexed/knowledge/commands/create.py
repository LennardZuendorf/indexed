"""Create command for adding collections (hardcoded subcommands)."""

from typing import List

import typer


def _is_cloud(url: str) -> bool:
    return url.endswith(".atlassian.net")


app = typer.Typer(help="Create new collections")


@app.command("files", help="Create a new collection from local files or folders.")
def create_files(
    collection: str = typer.Option(
        ...,
        "--collection",
        "-c",
        help="Name of the collection to create.",
    ),
    path: str = typer.Option(
        ...,
        "--path",
        "-p",
        help="Path to the root directory or file(s) to include in the collection.",
    ),
    include: List[str] = typer.Option(
        None,
        "--include",
        help="List of regex patterns for files/directories to include (can be specified multiple times).",
        show_default=False,
    ),
    exclude: List[str] = typer.Option(
        None,
        "--exclude",
        help="List of regex patterns for files/directories to exclude (can be specified multiple times).",
        show_default=False,
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast/--no-fail-fast",
        help="Stop and abort if the first file read error occurs.",
    ),
    use_cache: bool = typer.Option(
        True,
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged content.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete any existing collection with the same name before creating a new one.",
    ),
):
    """Create a collection from local files."""
    from indexed_config import ConfigService
    from core.v1.engine.services import SourceConfig, create as svc_create
    
    # Use default indexer
    DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
    
    cfg = SourceConfig(
        name=collection,
        type="localFiles",
        base_url_or_path=path,
        indexer=DEFAULT_INDEXER,
        reader_opts={
            "includePatterns": include or [],
            "excludePatterns": exclude or [],
            "failFast": fail_fast,
        },
    )

    config = ConfigService()
    svc_create([cfg], config_service=config, use_cache=use_cache, force=force)
    typer.echo(f"✓ Collection '{collection}' created from files")


@app.command(
    "jira",
    help="Create a new collection from Jira issues using a base JQL query."
)
def create_jira(
    collection: str = typer.Option(
        ...,
        "--collection",
        "-c",
        help="Name of the collection to create.",
    ),
    url: str = typer.Option(
        ...,
        "--url",
        "-u",
        help="Base URL of the Jira instance (e.g., https://foo.atlassian.net for cloud).",
    ),
    jql: str = typer.Option(
        ...,
        "--jql",
        "--query",
        "-q",
        help="Jira Query Language (JQL) expression for selecting issues. Example: project=MYPROJ",
    ),
    use_cache: bool = typer.Option(
        True,
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged issues.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete any existing collection with the same name before creating a new one.",
    ),
):
    from indexed_config import ConfigService
    from core.v1.engine.services import SourceConfig, create as svc_create

    # Use default indexer
    DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

    # Determine source type and build config
    if _is_cloud(url):
        source_type = "jiraCloud"
        reader_opts = {}  # Credentials will be read from env by connector
    else:
        source_type = "jira"
        reader_opts = {}  # Credentials will be read from env by connector

    cfg = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path=url,
        query=jql,
        indexer=DEFAULT_INDEXER,
        reader_opts=reader_opts,
    )

    config = ConfigService()
    svc_create([cfg], config_service=config, use_cache=use_cache, force=force)
    typer.echo(f"✓ Collection '{collection}' created from Jira")


@app.command(
    "confluence",
    help="Create a new collection from Confluence pages using a base CQL query."
)
def create_confluence(
    collection: str = typer.Option(
        ...,
        "--collection",
        "-c",
        help="Name of the collection to create.",
    ),
    url: str = typer.Option(
        ...,
        "--url",
        "-u",
        help="Base URL of the Confluence instance (e.g., https://foo.atlassian.net for cloud).",
    ),
    cql: str = typer.Option(
        ...,
        "--cql",
        "--query",
        "-q",
        help="Confluence Query Language (CQL) expression for selecting pages. Example: type=page AND space=\"ENG\"",
    ),
    read_all_comments: bool = typer.Option(
        True,
        "--read-all-comments/--first-level-comments",
        help="Read all nested comments if enabled, otherwise include only first-level comments.",
    ),
    use_cache: bool = typer.Option(
        True,
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged pages.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete any existing collection with the same name before creating a new one.",
    ),
):
    from indexed_config import ConfigService
    from core.v1.engine.services import SourceConfig, create as svc_create

    # Use default indexer
    DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

    # Determine source type and build config
    if _is_cloud(url):
        source_type = "confluenceCloud"
        reader_opts = {"readAllComments": read_all_comments}
    else:
        source_type = "confluence"
        reader_opts = {"readAllComments": read_all_comments}

    cfg = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path=url,
        query=cql,
        indexer=DEFAULT_INDEXER,
        reader_opts=reader_opts,
    )

    config = ConfigService()
    svc_create([cfg], config_service=config, use_cache=use_cache, force=force)
    typer.echo(f"✓ Collection '{collection}' created from Confluence")
