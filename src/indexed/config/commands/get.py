"""``indexed config get`` — read a single configuration value."""

from typing import Optional

import typer

# Import ConfigService at module level so tests can patch it.
from indexed.config import ConfigService
from indexed.cli.utils.console import console
from indexed.cli.utils.components import (
    create_detail_card,
    get_heading_style,
    print_info,
)

from ._helpers import (
    setup_command_logging,
    _is_sensitive_key,
    _masked_config_value,
)


def get_config(
    key: str = typer.Argument(..., help="Dot path (e.g., core.v1.indexing.chunk_size)"),
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
    """Get a single configuration value from the resolved (merged) config.

    Sensitive values (tokens, passwords) are masked and never echoed in
    cleartext (C1).
    """
    setup_command_logging(verbose, json_logs, log_level)

    config = ConfigService.instance()
    from indexed.config.path_utils import get_by_path

    raw = config.load_raw() or {}
    value = get_by_path(raw, key, default=None)

    from indexed.cli.utils.simple_output import is_simple_output, print_json

    if is_simple_output():
        # Preserve the real typed value for non-secrets so scripts get it;
        # mask secrets so they are never dumped in cleartext (C1).
        out = "*****" if (value is not None and _is_sensitive_key(key)) else value
        print_json({key: out})
        return

    if value is None:
        console.print()
        print_info(f"Key not found: {key}")
        console.print()
        return

    console.print()
    console.print(f"[{get_heading_style()}]Configuration Value[/{get_heading_style()}]")
    console.print()

    rows = [("Key", key), ("Value", _masked_config_value(key, value))]
    card = create_detail_card(title="Configuration Value", rows=rows)
    console.print(card)
    console.print()
