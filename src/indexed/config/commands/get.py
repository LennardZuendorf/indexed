"""``indexed config get`` — read a single configuration value."""

from typing import Any

import typer

from indexed.cli.utils.components import (
    create_detail_card,
    get_heading_style,
    print_info,
)
from indexed.cli.utils.console import console

# Aliased at module level (the command below is itself named ``get_config``) so
# tests can patch this seam without shadowing the Typer command.
from indexed.config import get_config as _resolve_config

from ._helpers import (
    _is_sensitive_key,
    _mask_sensitive_raw,
    _masked_config_value,
    setup_command_logging,
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
    log_level: str | None = typer.Option(
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

    config = _resolve_config()
    from indexed.config.path_utils import get_by_path

    raw = config.load_raw() or {}
    value = get_by_path(raw, key, default=None)

    from indexed.cli.utils.simple_output import is_simple_output, print_json

    if is_simple_output():
        # Never dump secrets in cleartext (C1). A dict value (the key is a
        # section/ancestor path like ``sources.jira``) is masked RECURSIVELY so
        # nested secret leaves (e.g. ``api_token``) are hidden; a sensitive leaf
        # value is masked directly. Non-secrets keep their real typed value so
        # scripts still get it.
        out: Any
        if isinstance(value, dict):
            out = _mask_sensitive_raw(value)
        elif value is not None and _is_sensitive_key(key):
            out = "*****"
        else:
            out = value
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
