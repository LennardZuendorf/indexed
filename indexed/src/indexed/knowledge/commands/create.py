"""Create command for adding collections (hardcoded subcommands)."""

import os
from typing import List

import typer


def _is_cloud(url: str) -> bool:
    return url.endswith(".atlassian.net")


def _require_env(names: List[str]) -> dict:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        typer.echo(f"Missing required env vars: {', '.join(missing)}", err=True)
        raise typer.Exit(1)
    return {n: os.getenv(n) for n in names}


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
    from indexed.app import svc_create, DEFAULT_INDEXER
    from core.v1.engine.services import SourceConfig

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

    svc_create([cfg], use_cache=use_cache, force=force)
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
    from indexed.app import svc_create, DEFAULT_INDEXER
    from core.v1.engine.services import SourceConfig

    if _is_cloud(url):
        env = _require_env(["ATLASSIAN_EMAIL", "ATLASSIAN_TOKEN"])
        reader_opts = {"email": env["ATLASSIAN_EMAIL"], "apiToken": env["ATLASSIAN_TOKEN"]}
        source_type = "jiraCloud"
    else:
        token = os.getenv("JIRA_TOKEN")
        login = os.getenv("JIRA_LOGIN")
        password = os.getenv("JIRA_PASSWORD")
        if not token and not (login and password):
            typer.echo("Provide JIRA_TOKEN or JIRA_LOGIN and JIRA_PASSWORD", err=True)
            raise typer.Exit(1)
        reader_opts = ({"token": token} if token else {"login": login, "password": password})
        source_type = "jira"

    cfg = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path=url,
        query=jql,
        indexer=DEFAULT_INDEXER,
        reader_opts=reader_opts,
    )

    svc_create([cfg], use_cache=use_cache, force=force)
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
    from indexed.app import svc_create, DEFAULT_INDEXER
    from core.v1.engine.services import SourceConfig

    if _is_cloud(url):
        env = _require_env(["ATLASSIAN_EMAIL", "ATLASSIAN_TOKEN"])
        reader_opts = {
            "email": env["ATLASSIAN_EMAIL"],
            "apiToken": env["ATLASSIAN_TOKEN"],
            "readAllComments": read_all_comments,
        }
        source_type = "confluenceCloud"
    else:
        token = os.getenv("CONF_TOKEN")
        login = os.getenv("CONF_LOGIN")
        password = os.getenv("CONF_PASSWORD")
        if not token and not (login and password):
            typer.echo("Provide CONF_TOKEN or CONF_LOGIN and CONF_PASSWORD", err=True)
            raise typer.Exit(1)
        reader_opts = (
            {"token": token} if token else {"login": login, "password": password}
        )
        reader_opts["readAllComments"] = read_all_comments
        source_type = "confluence"

    cfg = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path=url,
        query=cql,
        indexer=DEFAULT_INDEXER,
        reader_opts=reader_opts,
    )

    svc_create([cfg], use_cache=use_cache, force=force)
    typer.echo(f"✓ Collection '{collection}' created from Confluence")
