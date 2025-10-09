"""Create command group for creating collections from various sources."""

from typing import List
import typer

from core.v1.engine.services import SourceConfig

# --- simple styling helpers (ANSI) ---
RESET = "\033[0m"
BOLD = "\033[1m"

def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


create_app = typer.Typer(help="Create collections from various data sources")


@create_app.command("jira")
def create_jira(
    collection: str = typer.Option(
        "jira", "--collection", "-c", help="Name for the new collection"
    ),
    url: str = typer.Option(
        ..., "--url", "-u", help="Jira base URL (Cloud or Server/DC)"
    ),
    jql: str = typer.Option(
        ..., "--jql", help="Jira Query Language (JQL) to filter issues."
    ),
    index_name: str = typer.Option(
        None, "--index-name", help="Vector indexer configuration to use."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing collection if it exists."
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Disable read cache for improved performance."
    ),
) -> None:
    """Create a collection from Jira issues.
    
    Connects to Jira (Cloud or Server/DC) and creates a searchable collection
    from issues matching the provided JQL query. The collection will be indexed
    for semantic search and stored locally for fast retrieval.
    
    Examples:
        Create from Jira Cloud:
        $ indexed-cli create jira -c my-issues -u https://company.atlassian.net --jql "project = PROJ"
        
        Create from Jira Server:
        $ indexed-cli create jira -c server-issues -u https://jira.company.com --jql "assignee = currentUser()"
    """
    from .. import app as root

    indexer = index_name or root.DEFAULT_INDEXER
    cfg_type = "jiraCloud" if url.endswith(".atlassian.net") else "jira"
    
    typer.echo(f"\n🔗  {bold('Creating Jira collection')} '{collection}'…")
    typer.echo(f"   Source: {url}")
    typer.echo(f"   Query: {jql}")
    typer.echo(f"   Indexer: {indexer}\n")
    
    try:
        cfg = SourceConfig(
            name=collection,
            type=cfg_type,
            base_url_or_path=url,
            query=jql,
            indexer=indexer,
            reader_opts={},
        )
        root.svc_create([cfg], use_cache=not no_cache, force=force)
        typer.echo(f"✅  {bold('Successfully created')} Jira collection '{collection}'\n")
    except Exception as exc:  # pragma: no cover - error paths
        typer.echo(f"❌  Error creating collection: {exc}\n", err=True)
        raise typer.Exit(1)


@create_app.command("confluence")
def create_confluence(
    collection: str = typer.Option(
        "confluence", "--collection", "-c", help="Name for the new collection"
    ),
    url: str = typer.Option(
        ..., "--url", "-u", help="Confluence base URL (Cloud or Server/DC)"
    ),
    cql: str = typer.Option(
        ..., "--cql", help="Confluence Query Language (CQL) to filter pages"
    ),
    read_only_first_level_comments: bool = typer.Option(
        False,
        "--readOnlyFirstLevelComments",
        help="Only read top-level comments for better performance",
    ),
    index_name: str = typer.Option(
        None, "--index-name", help="Vector indexer configuration to use"
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing collection if it exists"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Disable read cache for improved performance"
    ),
) -> None:
    """Create a collection from Confluence pages and comments.
    
    Connects to Confluence (Cloud or Server/DC) and creates a searchable collection
    from pages and comments matching the provided CQL query. Pages are indexed with
    their content, metadata, and optionally comments for comprehensive search.
    
    Examples:
        Create from Confluence Cloud:
        $ indexed-cli create confluence -c wiki -u https://company.atlassian.net --cql "space = DEV"
        
        Create with comment filtering:
        $ indexed-cli create confluence -c docs -u https://wiki.company.com --cql "type = page" --readOnlyFirstLevelComments
    """
    from .. import app as root

    indexer = index_name or root.DEFAULT_INDEXER
    cfg_type = "confluenceCloud" if url.endswith(".atlassian.net") else "confluence"
    
    typer.echo(f"\n📚  {bold('Creating Confluence collection')} '{collection}'…")
    typer.echo(f"   Source: {url}")
    typer.echo(f"   Query: {cql}")
    if read_only_first_level_comments:
        typer.echo("   Comments: Top-level only")
    typer.echo(f"   Indexer: {indexer}\n")
    
    try:
        cfg = SourceConfig(
            name=collection,
            type=cfg_type,
            base_url_or_path=url,
            query=cql,
            indexer=indexer,
            reader_opts={"readOnlyFirstLevelComments": read_only_first_level_comments},
        )
        root.svc_create([cfg], use_cache=not no_cache, force=force)
        typer.echo(f"✅  {bold('Successfully created')} Confluence collection '{collection}'\n")
    except Exception as exc:  # pragma: no cover - error paths
        typer.echo(f"❌  Error creating collection: {exc}\n", err=True)
        raise typer.Exit(1)


@create_app.command("files")
def create_files(
    collection: str = typer.Option(
        ..., "--collection", "-c", help="Name for the new collection"
    ),
    base_path: str = typer.Option(
        ..., "--basePath", help="Root directory path to index files from"
    ),
    include_patterns: List[str] = typer.Option(
        [".*"], "--includePatterns", help="Regex patterns to include"
    ),
    exclude_patterns: List[str] = typer.Option(
        [], "--excludePatterns", help="Regex patterns to exclude"
    ),
    fail_fast: bool = typer.Option(
        False, "--failFast", help="Stop processing on first file error"
    ),
    index_name: str = typer.Option(
        None, "--index-name", help="Vector indexer configuration to use"
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing collection if it exists"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Disable read cache for improved performance"
    ),
) -> None:
    """Create a collection from local files and directories.
    
    Recursively scans the specified directory and creates a searchable collection
    from files matching the include/exclude patterns. Supports various file formats
    including text, markdown, code, PDFs, and more.
    
    Examples:
        Create from markdown files:
        $ indexed-cli create files -c docs --basePath ./documents --includePatterns ".*\\.md$"
        
        Create from code files, excluding tests:
        $ indexed-cli create files -c codebase --basePath ./src --includePatterns ".*\\.(py|js|ts)$" --excludePatterns ".*test.*"
        
        Create with strict error handling:
        $ indexed-cli create files -c strict-docs --basePath ./docs --failFast
    """
    from .. import app as root

    indexer = index_name or root.DEFAULT_INDEXER
    
    typer.echo(f"\n📁  {bold('Creating files collection')} '{collection}'…")
    typer.echo(f"   Source: {base_path}")
    typer.echo(f"   Include patterns: {', '.join(include_patterns)}")
    if exclude_patterns:
        typer.echo(f"   Exclude patterns: {', '.join(exclude_patterns)}")
    typer.echo(f"   Indexer: {indexer}")
    if fail_fast:
        typer.echo("   Error handling: Fail fast")
    typer.echo()
    
    try:
        cfg = SourceConfig(
            name=collection,
            type="localFiles",
            base_url_or_path=base_path,
            query=None,
            indexer=indexer,
            reader_opts={
                "includePatterns": include_patterns,
                "excludePatterns": exclude_patterns,
                "failFast": fail_fast,
            },
        )
        root.svc_create([cfg], use_cache=not no_cache, force=force)
        typer.echo(f"✅  {bold('Successfully created')} files collection '{collection}'\n")
    except Exception as exc:  # pragma: no cover - error paths
        typer.echo(f"❌  Error creating collection: {exc}\n", err=True)
        raise typer.Exit(1)
