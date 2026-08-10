"""``indexed config set`` — set a configuration value at a dot-path."""

from typing import Any

import typer
from loguru import logger
from rich.markup import escape

from indexed.cli.utils.components import (
    create_detail_card,
    get_heading_style,
    get_secondary_style,
    get_warning_style,
    print_error,
    print_success,
    print_warning,
)
from indexed.cli.utils.console import console

# Import get_config at module level so tests can patch it.
from indexed.config import get_config

from ._helpers import (
    _coerce_value,
    _is_sensitive_key,
    _masked_config_value,
    setup_command_logging,
)


def set_config(
    key: str = typer.Argument(..., help="Dot path (e.g., core.v1.indexing.chunk_size)"),
    value: str = typer.Argument(..., help="Value (auto-coerced)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview change without saving"
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
    log_level: str | None = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        rich_help_panel="Logging",
    ),
) -> None:
    """Set a configuration value at dot-path in workspace config."""
    setup_command_logging(verbose, json_logs, log_level)

    config = get_config()
    coerced = _coerce_value(value)

    # Get old value if exists
    try:
        old_raw = config.load_raw() or {}
        from indexed.config.path_utils import get_by_path

        old_value = get_by_path(old_raw, key, default=None)
    except Exception:
        old_value = None

    if dry_run:
        # Preview mode
        console.print()
        console.print(
            f"[{get_heading_style()}]Configuration Preview[/{get_heading_style()}]"
        )
        console.print()

        rows = [("Key", key)]
        if old_value is not None:
            rows.append(("Previous", _masked_config_value(key, old_value)))
        rows.append(("New", _masked_config_value(key, coerced)))

        card = create_detail_card(title="Change Summary", rows=rows)
        console.print(card)
        console.print()
        console.print(
            f"[{get_secondary_style()}]Preview only - not saved (remove --dry-run to save)[/{get_secondary_style()}]"
        )
        console.print()
        return

    is_secret = _is_sensitive_key(key)
    # Secrets are written to .env as-typed (no type coercion, e.g. a purely
    # numeric token must not silently become an int).
    write_value = value if is_secret else coerced

    field_info: dict[str, Any] = {"sensitive": is_secret}
    if is_secret:
        # Resolve the connector-declared .env key (e.g. "sources.jira.api_token"
        # -> "ATLASSIAN_TOKEN") so the secret lands where the connector reads
        # it, instead of a fallback derived from the last dot-path segment.
        resolved_env_var = config.resolve_sensitive_env_var(key)
        if resolved_env_var:
            field_info["env_var"] = resolved_env_var
        else:
            fallback_env_var = key.split(".")[-1].upper()
            logger.warning(
                "No registered connector field for '{}'; saving to .env key "
                "'{}', which may not be what the connector reads",
                key,
                fallback_env_var,
            )
            console.print()
            print_warning(
                f"No connector mapping found for '{key}' — saved under "
                f"'.env' key '{fallback_env_var}' (best-effort fallback)"
            )

    try:
        config.set_value(key, write_value, field_info=field_info)

        # Validate
        errs = config.validate()
        if errs:
            console.print()
            print_warning("Validation warnings detected")
            console.print()
            for path, msg in errs:
                # msg is a Pydantic ValidationError string, which echoes the
                # rejected input value verbatim — escape before it enters
                # this markup string.
                console.print(
                    f"  [{get_warning_style()}]•[/{get_warning_style()}] "
                    f"{escape(path)}: {escape(msg)}"
                )
            console.print()

        # Show success with change summary
        console.print()
        console.print(
            f"[{get_heading_style()}]Configuration Updated[/{get_heading_style()}]"
        )
        console.print()

        rows = [("Key", key)]
        if old_value is not None:
            rows.append(("Previous", _masked_config_value(key, old_value)))
        rows.append(("New", _masked_config_value(key, coerced)))

        card = create_detail_card(title="Change Summary", rows=rows)
        console.print(card)
        console.print()
        if is_secret:
            print_success("Secret saved to .env (kept out of config.toml)")
        else:
            # F4: name the actual resolved destination (global or workspace
            # config.toml) instead of a hardcoded literal.
            print_success("Configuration saved")
            target_path = config.store.resolved_config_path()
            # target_path is a filesystem path (may contain the user's
            # workspace/home directory name) — escape before it enters
            # this markup string.
            console.print(
                f"[{get_secondary_style()}]Location: {escape(str(target_path))}[/{get_secondary_style()}]",
                soft_wrap=True,
            )
        console.print()

    except Exception as e:
        console.print()
        print_error(f"Error: {e}")
        raise typer.Exit(1)
