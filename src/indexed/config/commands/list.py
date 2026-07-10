"""``indexed config list`` — show the resolved configuration."""

from typing import Optional

import typer

# Import ConfigService at module level so tests can patch it.
from indexed.config import ConfigService

from ._helpers import setup_command_logging, _mask_sensitive_raw
from ._render import render_config_overview


def list_config(
    section: Optional[str] = typer.Argument(
        None,
        help="Section to list (sources, core, logging, mcp, performance)",
    ),
    show_defaults: bool = typer.Option(
        False,
        "--show-defaults",
        "--defaults",
        "-d",
        help="Show all default values (not just select ones)",
    ),
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
    """List the resolved configuration (defaults + workspace + env).

    Examples:
        indexed config list             # Custom values + select defaults
        indexed config list sources     # Only the sources config
        indexed config list --defaults  # All values including defaults
    """
    setup_command_logging(verbose, json_logs, log_level)

    config = ConfigService.instance()
    raw = config.load_raw()

    from indexed.cli.utils.simple_output import is_simple_output, print_json

    if is_simple_output():
        # Mask secrets so a value reaching merged config is never dumped (C1).
        print_json(_mask_sensitive_raw(raw))
        return

    render_config_overview(config, raw, section, show_defaults)
