"""``indexed config validate`` — validate the active configuration."""

from typing import Optional
from collections import defaultdict

import typer
from rich.panel import Panel
from rich.console import Group
from rich.text import Text

# Import get_config at module level so tests can patch it.
from indexed.config import get_config
from indexed.cli.utils.console import console
from indexed.cli.utils.components import (
    get_heading_style,
    get_error_style,
    get_secondary_style,
    get_card_padding,
    get_detail_card_width,
    print_success,
    print_error,
)

from ._helpers import setup_command_logging


def validate(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose (INFO) logging",
        rich_help_panel="Logging",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON (structured)",
        rich_help_panel="Logging",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        rich_help_panel="Logging",
    ),
) -> None:
    """
    Validate the active configuration against registered validation rules.

    Prints a success message when no issues are found, and grouped, sectioned
    error cards when issues exist. Exits with status code 1 on any error.
    """
    setup_command_logging(verbose, json_logs, log_level)

    config = get_config()
    errs = config.validate()

    console.print()
    console.print(
        f"[{get_heading_style()}]Configuration Validation[/{get_heading_style()}]"
    )
    console.print()

    if not errs:
        # Success case - no errors
        print_success("All configuration values are valid")
        console.print()
        return

    # Group errors by section (first part of path)
    grouped_errors = defaultdict(list)
    for path, message in errs:
        section = path.split(".")[0] if "." in path else "general"
        grouped_errors[section].append((path, message))

    # Create error cards for each section
    for section in sorted(grouped_errors.keys()):
        section_errors = grouped_errors[section]

        # Format section name
        title = section.replace("_", " ").title() + " Errors"

        # Build error list
        error_lines = []
        for path, message in section_errors:
            error_lines.append(Text(f"• {path}: {message}"))

        # Add suggestions if applicable
        if any("url" in p for p, _ in section_errors):
            error_lines.append(Text())
            error_lines.append(
                Text(
                    "Suggestion: Use format https://company.atlassian.net",
                    style=get_secondary_style(),
                )
            )

        content = Group(*error_lines)

        error_card = Panel(
            content,
            title=f"[{get_error_style()}]{title}[/{get_error_style()}]",
            border_style=get_error_style(),
            padding=get_card_padding(),
            width=get_detail_card_width(),
        )
        console.print(error_card)
        console.print()

    # Summary
    error_count = len(errs)
    plural = "error" if error_count == 1 else "errors"
    print_error(f"{error_count} validation {plural} found")
    console.print()

    raise typer.Exit(1)
