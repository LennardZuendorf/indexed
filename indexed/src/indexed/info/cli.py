"""Information and help commands for Indexed CLI.

Provides commands to access documentation and view license information.
"""

import webbrowser
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error

import typer
from rich.markdown import Markdown

from ..utils.console import console
from ..utils.components.theme import (
    get_accent_style,
    get_error_style,
    get_success_style,
    get_secondary_style,
    get_dim_style,
)

app = typer.Typer(
    help="Information & Help Commands",
    rich_markup_mode="rich",
)

# Documentation URL mappings
DOC_BASE_URL = "https://indexed.ignitr.dev/docs"
DOC_URLS = {
    "index": f"{DOC_BASE_URL}/indexing",
    "indexing": f"{DOC_BASE_URL}/indexing",
    "config": f"{DOC_BASE_URL}/configuration",
    "configuration": f"{DOC_BASE_URL}/configuration",
    "mcp": f"{DOC_BASE_URL}/mcp",
    "confluence": f"{DOC_BASE_URL}/indexing/connectors/confluence",
    "files": f"{DOC_BASE_URL}/indexing/connectors/files",
    "jira": f"{DOC_BASE_URL}/indexing/connectors/jira",
}


@app.command("docs")
def docs(
    topic: Optional[str] = typer.Argument(
        None, help="Specific command or topic (index, config, mcp, confluence, files, jira)"
    )
) -> None:
    """Open documentation in web browser.

    Opens the Indexed documentation in your default web browser. You can optionally
    specify a topic to open command-specific documentation pages.

    Examples:
        indexed docs              # Open main documentation
        indexed docs index        # Open indexing documentation
        indexed docs config       # Open configuration documentation
        indexed docs mcp          # Open MCP server documentation
        indexed docs confluence   # Open Confluence connector docs
    """
    # Determine URL based on topic
    if topic is None:
        url = DOC_BASE_URL
        topic_display = "main documentation"
    else:
        topic_lower = topic.lower()
        if topic_lower in DOC_URLS:
            url = DOC_URLS[topic_lower]
            topic_display = f"{topic} documentation"
        else:
            # Invalid topic - show helpful error
            console.print()
            console.print(
                f"[{get_error_style()}]❌ Unknown documentation topic: {topic}[/{get_error_style()}]"
            )
            console.print()
            console.print(f"[{get_accent_style()}]Available topics:[/{get_accent_style()}]")
            console.print()
            for topic_name in sorted(DOC_URLS.keys()):
                console.print(f"  • {topic_name}")
            console.print()
            console.print(f"[{get_secondary_style()}]Usage: indexed docs [TOPIC][/{get_secondary_style()}]")
            console.print()
            raise typer.Exit(1)

    # Open in browser
    try:
        webbrowser.open(url)
        console.print()
        console.print(
            f"[{get_success_style()}]✓[/{get_success_style()}] Opening {topic_display} in browser..."
        )
        console.print(f"[{get_secondary_style()}]{url}[/{get_secondary_style()}]")
        console.print()
    except Exception as e:
        console.print()
        console.print(
            f"[{get_error_style()}]❌ Failed to open browser: {e}[/{get_error_style()}]"
        )
        console.print(f"[{get_secondary_style()}]Visit manually: {url}[/{get_secondary_style()}]")
        console.print()
        raise typer.Exit(1)


@app.command("license")
def license_terms() -> None:
    """Display license and terms & conditions.

    Displays the Indexed software license in a scrollable markdown view.
    The license uses the Sustainable Use License with specific usage terms.

    Use arrow keys or Page Up/Down to scroll, Q to quit.
    """
    # Remote LICENSE URL (always up-to-date from GitHub)
    license_url = "https://raw.githubusercontent.com/LennardZuendorf/indexed/refs/heads/main/LICENSE"
    
    license_content = None
    source = None

    # Try to fetch from remote URL first (always up-to-date)
    try:
        with urllib.request.urlopen(license_url, timeout=5) as response:
            license_content = response.read().decode("utf-8")
            source = "remote"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        # Remote fetch failed, fall back to local file
        pass

    # Fall back to local LICENSE file if remote fetch failed
    if license_content is None:
        possible_paths = [
            # From installed package (relative to this file)
            Path(__file__).parent.parent.parent.parent.parent / "LICENSE",
            # Relative to current working directory
            Path.cwd() / "LICENSE",
        ]

        license_path = None
        for path in possible_paths:
            if path.exists():
                license_path = path
                break

        if license_path is None:
            console.print()
            console.print(
                f"[{get_error_style()}]❌ LICENSE file not found[/{get_error_style()}]"
            )
            console.print()
            console.print(
                f"[{get_secondary_style()}]Could not fetch from remote and no local file found.[/{get_secondary_style()}]"
            )
            console.print()
            console.print(
                f"[{get_secondary_style()}]View online: {license_url.replace('/refs/heads/main/', '/blob/main/')}[/{get_secondary_style()}]"
            )
            console.print()
            raise typer.Exit(1)

        try:
            license_content = license_path.read_text(encoding="utf-8")
            source = "local"
        except Exception as e:
            console.print()
            console.print(
                f"[{get_error_style()}]❌ Failed to read LICENSE: {e}[/{get_error_style()}]"
            )
            console.print()
            raise typer.Exit(1)

    # Display license with pager
    try:
        # Create markdown object with the license content
        md = Markdown(license_content)

        # Display with pager for scrolling
        console.print()
        console.print(
            f"[{get_accent_style()}]Indexed Software License[/{get_accent_style()}]"
        )
        
        # Show source indicator
        if source == "remote":
            console.print(
                f"[{get_dim_style()}](Loaded from GitHub repository)[/{get_dim_style()}]"
            )
        elif source == "local":
            console.print(
                f"[{get_dim_style()}](Using local copy - may not reflect latest version)[/{get_dim_style()}]"
            )
        
        console.print()

        # Use pager context manager for scrollable view
        with console.pager(styles=True):
            console.print(md)

    except Exception as e:
        console.print()
        console.print(
            f"[{get_error_style()}]❌ Failed to display LICENSE: {e}[/{get_error_style()}]"
        )
        console.print()
        raise typer.Exit(1)


def cli_main() -> None:
    """Entry point for info CLI."""
    app()


if __name__ == "__main__":
    cli_main()

