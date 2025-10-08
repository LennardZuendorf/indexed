"""Create command for adding collections."""

import os
import typer
from core.v1 import Index
from connectors import FileSystemConnector, JiraConnector, JiraCloudConnector, ConfluenceConnector, ConfluenceCloudConnector

app = typer.Typer(help="Create new collections")


@app.command("files")
def create_files(
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
    path: str = typer.Option(..., "--path", "-p", help="Path to files"),
    include: list[str] = typer.Option(None, "--include", help="Include patterns"),
    exclude: list[str] = typer.Option(None, "--exclude", help="Exclude patterns"),
):
    """Create collection from local files."""
    connector = FileSystemConnector(
        path=path,
        include_patterns=include,
        exclude_patterns=exclude
    )
    
    index = Index()
    typer.echo(f"Creating collection '{name}' from {path}...")
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")


@app.command("jira")
def create_jira(
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
    url: str = typer.Option(..., "--url", "-u", help="Jira URL"),
    query: str = typer.Option(..., "--query", "-q", help="JQL query"),
):
    """Create collection from Jira."""
    # Detect cloud vs server
    is_cloud = url.endswith(".atlassian.net")
    
    if is_cloud:
        email = os.getenv("ATLASSIAN_EMAIL")
        token = os.getenv("ATLASSIAN_TOKEN")
        if not email or not token:
            typer.echo("Error: ATLASSIAN_EMAIL and ATLASSIAN_TOKEN required", err=True)
            raise typer.Exit(1)
        connector = JiraCloudConnector(url=url, query=query, email=email, api_token=token)
    else:
        token = os.getenv("JIRA_TOKEN")
        login = os.getenv("JIRA_LOGIN")
        password = os.getenv("JIRA_PASSWORD")
        connector = JiraConnector(url=url, query=query, token=token, login=login, password=password)
    
    index = Index()
    typer.echo(f"Creating collection '{name}' from Jira...")
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")


@app.command("confluence")
def create_confluence(
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
    url: str = typer.Option(..., "--url", "-u", help="Confluence URL"),
    query: str = typer.Option(..., "--query", "-q", help="CQL query"),
):
    """Create collection from Confluence."""
    # Detect cloud vs server
    is_cloud = url.endswith(".atlassian.net")
    
    if is_cloud:
        email = os.getenv("ATLASSIAN_EMAIL")
        token = os.getenv("ATLASSIAN_TOKEN")
        if not email or not token:
            typer.echo("Error: ATLASSIAN_EMAIL and ATLASSIAN_TOKEN required", err=True)
            raise typer.Exit(1)
        connector = ConfluenceCloudConnector(url=url, query=query, email=email, api_token=token)
    else:
        token = os.getenv("CONF_TOKEN")
        login = os.getenv("CONF_LOGIN")
        password = os.getenv("CONF_PASSWORD")
        connector = ConfluenceConnector(url=url, query=query, token=token, login=login, password=password)
    
    index = Index()
    typer.echo(f"Creating collection '{name}' from Confluence...")
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")
