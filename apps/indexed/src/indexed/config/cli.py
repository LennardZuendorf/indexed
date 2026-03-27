"""Config command for managing index configuration."""

import json
import webbrowser
from typing import Any, Optional
from collections import defaultdict
from pathlib import Path

import typer

# Raw Rich components — used for interactive selection menus and validation error cards
# that don't fit the card-based design system components
from rich.panel import Panel
from rich.console import Group
from rich.text import Text
from rich.table import Table
from rich import box

from indexed_config import ConfigService
from ..utils.console import console
from ..utils.components import (
    create_info_card,
    create_detail_card,
    create_key_value_panel,
    create_simple_key_value_panel,
    get_card_padding,
    get_default_style,
    get_detail_card_width,
    get_heading_style,
    get_success_style,
    get_error_style,
    get_warning_style,
    get_secondary_style,
    get_accent_style,
    get_dim_style,
    print_success,
    print_error,
    print_warning,
    print_info,
    ICON_SUCCESS,
)
from indexed_config.path_utils import set_by_path

app = typer.Typer(help="Manage configuration")


# ============================================================================
# Constants
# ============================================================================

# Environment variable mappings for sensitive config keys
_ENV_VAR_MAPPINGS = {
    "api_token": ["ATLASSIAN_TOKEN", "JIRA_TOKEN", "CONF_TOKEN"],
    "token": ["ATLASSIAN_TOKEN", "JIRA_TOKEN", "CONF_TOKEN"],
    "email": ["ATLASSIAN_EMAIL"],
    "password": ["JIRA_PASSWORD", "CONF_PASSWORD"],
}


# ============================================================================
# Helper Functions
# ============================================================================


def _value_to_default_str(value: Any) -> str:
    """
    Convert a config value to its string representation for prompts.

    Parameters:
        value: The config value to convert (bool, list, dict, None, or other).

    Returns:
        str: String representation suitable for use as a prompt default.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (list, dict)):
        return json.dumps(value)
    elif value is None:
        return ""
    else:
        return str(value)


def _coerce_value(value: str) -> Any:
    """
    Convert a string to an appropriate Python type.

    Attempts to interpret the input as a boolean, integer, float, or JSON value (list/dict); if none apply, returns the original string.

    Parameters:
        value (str): The input string to coerce.

    Returns:
        The coerced value as an `int`, `float`, `bool`, `list`, `dict`, or the original `str`.
    """
    # Try bool first
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"

    # Try int (handles both positive and negative integers properly)
    try:
        return int(value)
    except ValueError:
        pass

    # Try float
    try:
        return float(value)
    except ValueError:
        pass

    # Try JSON (for lists/dicts)
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        pass

    # Return original string if no conversion succeeded
    return value


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Flatten nested dictionary with dot notation keys.

    Args:
        d: Dictionary to flatten
        parent_key: Parent key prefix
        sep: Separator for keys

    Returns:
        Flattened dictionary
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _group_config_by_section(config_dict: dict) -> dict[str, dict[str, Any]]:
    """
    Group configuration entries by their top-level section.

    Flattens nested keys into dot-separated paths and returns a mapping where each top-level
    section name maps to a dictionary of its sub-keys (the remainder of the path) to values.

    Returns:
        dict[str, dict[str, Any]]: Mapping from section name to a dict of sub-key -> value.
    """
    # Flatten the config first
    flat_config = _flatten_dict(config_dict)

    # Group by top-level key
    grouped = defaultdict(dict)
    for key, value in flat_config.items():
        parts = key.split(".", 1)
        section = parts[0]
        subkey = parts[1] if len(parts) > 1 else key
        grouped[section][subkey] = value

    return dict(grouped)


def _format_config_value(value: Any) -> str:
    """
    Produce a display-friendly string for a configuration value.

    Formats common config types for human-readable output: booleans become "true"/"false", empty lists or dicts become "(empty)", None becomes "(not set)", non-empty lists are joined with ", ", and dicts are summarized as "(N items)".

    Returns:
        str: Display-friendly representation of the provided value.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (list, tuple)):
        if not value:
            return "(empty)"
        return ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        if not value:
            return "(empty)"
        return f"({len(value)} items)"
    elif value is None:
        return "(not set)"
    else:
        return str(value)


def _is_sensitive_key(key: str) -> bool:
    """
    Determine whether a configuration key should be treated as sensitive for display.

    Parameters:
        key (str): Dot-separated configuration key (e.g., "jira.api_token"); only the last segment is inspected.

    Returns:
        true if the last key segment contains any of: "api_token", "token", "password", or "secret"; false otherwise.
    """
    sensitive_patterns = ["api_token", "token", "password", "secret"]
    key_lower = key.lower()
    # Check last part of dot-path (e.g., "jira.api_token" -> "api_token")
    key_name = key.split(".")[-1].lower() if "." in key else key_lower
    return any(pattern in key_name for pattern in sensitive_patterns)


def _get_sensitive_env_value(key: str) -> Optional[str]:
    """
    Return a masked value if the given configuration key has a corresponding environment variable set.

    Parameters:
        key (str): Dot-path or simple key name to check (e.g., "api_token" or "jira.email").

    Returns:
        Optional[str]: The masked string "*****" if a relevant environment variable is present for the key, None otherwise.
    """
    import os

    # Get the key name (last part of dot-path)
    key_name = key.split(".")[-1].lower() if "." in key else key.lower()

    # Check env vars for this key type
    env_vars = _ENV_VAR_MAPPINGS.get(key_name, [])
    for env_var in env_vars:
        if os.getenv(env_var):
            return "*****"

    return None


def _create_section_card(section_name: str, section_data: dict[str, Any]) -> Panel:
    """
    Render a UI card summarizing a configuration section.

    Displays each config key (dot-paths shown with separators) alongside a formatted value. If the section has no keys, includes a single "Status" row with "(no configuration)".

    Parameters:
        section_name (str): Section identifier used as the card title.
        section_data (dict[str, Any]): Mapping of configuration keys to their values for the section.

    Returns:
        Panel: A Rich Panel containing the section title and key/value rows.
    """
    # Format section name nicely
    title = section_name.replace("_", " ").title()

    # Create rows from section data
    rows = []
    for key, value in sorted(section_data.items()):
        # Format nested keys with indentation
        display_key = key.replace(".", " › ")
        formatted_value = _format_config_value(value)
        rows.append((display_key, formatted_value))

    if not rows:
        rows.append(("Status", "(no configuration)"))

    return create_info_card(title=title, rows=rows)


def _get_full_config_schema() -> dict[str, dict[str, Any]]:
    """
    Return a mapping of configuration sections to their default configuration values.

    Attempts to obtain defaults from Pydantic models (core.v1 indexing, embedding, search, storage; MCP; performance; logging). If those models are unavailable, falls back to a minimal built-in defaults schema for core.v1 and logging. The returned structure includes top-level sections such as "core" (with "v1" sub-sections), "mcp", "performance", "logging", and "sources" (empty when no defaults are defined).

    Returns:
        dict[str, dict[str, Any]]: Mapping of section names to dictionaries of default configuration values.
    """
    # Import Pydantic models for defaults
    try:
        from core.v1.config_models import (
            CoreV1IndexingConfig,
            CoreV1EmbeddingConfig,
            CoreV1SearchConfig,
            CoreV1StorageConfig,
            MCPConfig,
            PerformanceConfig,
            LoggingConfig,
        )

        # Get defaults from Pydantic models by instantiating with no args
        indexing_defaults = CoreV1IndexingConfig().model_dump()
        embedding_defaults = CoreV1EmbeddingConfig().model_dump()
        search_defaults = CoreV1SearchConfig().model_dump()
        storage_defaults = CoreV1StorageConfig().model_dump()
        mcp_defaults = MCPConfig().model_dump()
        performance_defaults = PerformanceConfig().model_dump()
        logging_defaults = LoggingConfig().model_dump()

        return {
            "core": {
                "v1": {
                    "indexing": indexing_defaults,
                    "embedding": embedding_defaults,
                    "search": search_defaults,
                    "storage": storage_defaults,
                }
            },
            "mcp": mcp_defaults,
            "performance": performance_defaults,
            "logging": logging_defaults,
            # Sources don't have defaults - they're user-configured
            "sources": {},
        }
    except ImportError:
        # Fallback if core models aren't available
        return {
            "core": {
                "v1": {
                    "indexing": {
                        "chunk_size": 512,
                        "chunk_overlap": 50,
                        "batch_size": 32,
                    },
                    "embedding": {
                        "provider": "sentence-transformers",
                        "model_name": "all-MiniLM-L6-v2",
                        "batch_size": 64,
                    },
                    "search": {
                        "max_docs": 10,
                        "max_chunks": 30,
                        "include_full_text": False,
                    },
                }
            },
            "logging": {
                "level": "WARNING",
            },
            "sources": {},
        }


def _merge_with_defaults(
    raw_config: dict[str, Any],
    defaults_schema: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Merge raw config with defaults, tracking which values are manually set.

    Args:
        raw_config: The raw config loaded from files/env
        defaults_schema: The full schema with default values

    Returns:
        Dictionary where each key maps to {"value": Any, "is_default": bool}
        grouped by section.
    """
    # Flatten both configs for comparison
    flat_raw = _flatten_dict(raw_config) if raw_config else {}
    flat_defaults = _flatten_dict(defaults_schema) if defaults_schema else {}

    # Build result with tracking
    result: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    # All keys from both sources
    all_keys = set(flat_raw.keys()) | set(flat_defaults.keys())

    for key in sorted(all_keys):
        # Determine section (first part of dot-path)
        parts = key.split(".", 1)
        section = parts[0]
        subkey = parts[1] if len(parts) > 1 else key

        # Skip workspace - handled separately
        if section == "workspace":
            continue

        if key in flat_raw:
            # Value was explicitly set
            result[section][subkey] = {
                "value": flat_raw[key],
                "is_default": False,
            }
        elif key in flat_defaults:
            # Using default value
            result[section][subkey] = {
                "value": flat_defaults[key],
                "is_default": True,
            }

    return dict(result)


def _get_available_config_schema() -> dict[str, dict[str, Any]]:
    """Get available configuration schema with default values.

    Returns:
        Dictionary of available sections and their keys with defaults

    Note: This is kept for backwards compatibility with the interactive
    update command. For inspect, use _get_full_config_schema() instead.
    """
    return {
        "index": {
            "embedding_model": "sentence-transformers/all-mpnet-base-v2",
            "use_gpu": False,
        },
        "search": {
            "include_full_text": True,
            "max_results": 10,
        },
        "sources": {
            # Files connector
            "files.path": "./data",
            "files.include_patterns": ["*.md", "*.txt"],
            "files.exclude_patterns": [],
            # Jira connector
            "jira.url": "https://your-domain.atlassian.net",
            "jira.email": "your-email@example.com",
            "jira.api_token": "",
            "jira.query": "project = PROJ",
            # Confluence connector
            "confluence.url": "https://your-domain.atlassian.net/wiki",
            "confluence.email": "your-email@example.com",
            "confluence.api_token": "",
            "confluence.query": "space = SPACE",
            "confluence.read_all_comments": True,
        },
        "logging": {
            "level": "WARNING",
        },
    }


def _select_section(grouped_config: dict[str, dict[str, Any]]) -> Optional[str]:
    """
    Present an interactive menu for selecting a configuration section.

    Parameters:
        grouped_config (dict[str, dict[str, Any]]): Mapping of section names to their keys and values used to determine which sections are configured.

    Returns:
        Optional[str]: The chosen section name, or `None` if the user exits or makes no valid selection.
    """
    console.print()
    console.print(
        f"[{get_heading_style()}]Select Configuration Section[/{get_heading_style()}]"
    )
    console.print()

    # Get available schema
    schema = _get_available_config_schema()

    # Combine existing and available sections
    existing_sections = set(grouped_config.keys())
    all_sections = sorted(existing_sections | set(schema.keys()))

    # Create a table for better visual organization
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=False)
    table.add_column("Index", style=get_accent_style(), width=4)
    table.add_column("Section", style=get_default_style(), min_width=30)
    table.add_column("Status", style=get_secondary_style())

    for idx, section in enumerate(all_sections, 1):
        # Format section name nicely
        display_name = section.replace("_", " ").replace(".", " › ").title()

        if section in existing_sections:
            key_count = len(grouped_config[section])
            plural = "key" if key_count == 1 else "keys"
            status = f"{ICON_SUCCESS} {key_count} {plural} configured"
            table.add_row(f"{idx}.", display_name, status)
        else:
            # Section not configured - show number of available default values
            section_schema = schema.get(section, {})
            default_count = len(section_schema)
            if default_count > 0:
                plural = "value" if default_count == 1 else "values"
                status_text = f"using {default_count} default {plural}"
            else:
                status_text = "not configured"
            table.add_row(
                f"{idx}.", display_name, Text(status_text, style=get_secondary_style())
            )

    console.print(table)
    console.print()
    console.print(f"  [{get_accent_style()}]0.[/{get_accent_style()}] Exit")
    console.print()

    choice = typer.prompt("Select section or exit", default="0")

    try:
        choice_idx = int(choice)
        if choice_idx == 0:
            return None
        if 1 <= choice_idx <= len(all_sections):
            return all_sections[choice_idx - 1]
    except ValueError:
        pass

    print_error("Invalid choice")
    return None


def _group_keys_by_prefix(keys: list[str]) -> dict[str, list[str]]:
    """Group keys by their prefix (first part before dot).

    Args:
        keys: List of keys to group

    Returns:
        Dictionary mapping group name to list of keys
    """
    groups = defaultdict(list)

    for key in keys:
        # Group by first part before dot (e.g., "files.path" -> "files")
        if "." in key:
            group = key.split(".")[0]
        else:
            group = "general"

        groups[group].append(key)

    return dict(groups)


def _select_key(
    section_name: str, section_data: dict[str, Any]
) -> Optional[tuple[str, bool]]:
    """
    Prompt the user to select a configuration key within the given section.

    Parameters:
        section_name (str): The section identifier (dot-notated) to list keys for.
        section_data (dict[str, Any]): Existing key→value mappings in the section.

    Returns:
        tuple[str, bool] | None: A `(selected_key, is_new)` tuple where `is_new` is `True` if the selected key is not currently set, or `None` if the user cancelled or chose to go back.
    """
    console.print()
    console.print(
        f"[{get_heading_style()}]{section_name.replace('_', ' ').replace('.', ' › ').title()} Settings[/{get_heading_style()}]"
    )
    console.print()

    # Get available keys from schema
    schema = _get_available_config_schema()
    available_keys = schema.get(section_name, {}).keys()

    # Combine existing and available keys
    existing_keys = set(section_data.keys())
    all_keys = sorted(existing_keys | set(available_keys))

    # Group keys by prefix for better organization
    grouped_keys = _group_keys_by_prefix(all_keys)

    # Create a table for better visual organization
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=False)
    table.add_column("Index", style=get_accent_style(), width=4)
    table.add_column("Key", style=get_default_style())
    table.add_column("Value", style=get_secondary_style())

    idx = 1
    key_mapping = []

    # Display keys grouped by prefix
    for group_idx, (group, keys) in enumerate(sorted(grouped_keys.items())):
        # Add visual separator between groups (except first)
        if group_idx > 0:
            table.add_row("", "", "")

        # Add group header
        group_display = group.replace("_", " ").title()
        if group != "general":
            table.add_row(
                "", Text(f"━━ {group_display} ━━", style=get_secondary_style()), ""
            )

        # Add keys in this group
        for key in sorted(keys):
            # Remove group prefix and format nicely (e.g., "files.include_patterns" -> "Include Patterns")
            if "." in key:
                display_key = key.split(".", 1)[1].replace("_", " ").title()
            else:
                display_key = key.replace("_", " ").title()

            if key in existing_keys:
                current_value = _format_config_value(section_data[key])
                # Mask sensitive values that are set
                if _is_sensitive_key(key) and current_value not in (
                    "(not set)",
                    "(empty)",
                ):
                    current_value = "*****"
                # Truncate long values for display
                elif len(str(current_value)) > 50:
                    current_value = str(current_value)[:47] + "..."
                table.add_row(f"{idx}.", display_key, current_value)
            else:
                # Check if sensitive value is set via environment variable
                env_value = _get_sensitive_env_value(key)
                if env_value:
                    table.add_row(
                        f"{idx}.",
                        display_key,
                        Text(env_value, style=get_secondary_style()),
                    )
                else:
                    table.add_row(
                        f"{idx}.",
                        display_key,
                        Text("(not set)", style=get_secondary_style()),
                    )

            key_mapping.append(key)
            idx += 1

    console.print(table)
    console.print()
    console.print(f"  [{get_accent_style()}]0.[/{get_accent_style()}] Back")
    console.print()

    choice = typer.prompt("Select setting or go back", default="0")

    try:
        choice_idx = int(choice)
        if choice_idx == 0:
            return None
        if 1 <= choice_idx <= len(key_mapping):
            selected_key = key_mapping[choice_idx - 1]
            is_new = selected_key not in existing_keys
            return (selected_key, is_new)
    except ValueError:
        pass

    print_error("Invalid choice")
    return None


def _prompt_for_value(
    key: str, current_value: Any, is_new: bool = False, section_name: str = ""
) -> Optional[Any]:
    """
    Prompt the user to enter a configuration value for a given key, showing the current or suggested default.

    If the user cancels (presses Enter with no input and no default), returns None.

    Parameters:
        key (str): Dot-path configuration key being edited (e.g., "core.v1.indexing.chunk_size").
        current_value (Any): Existing value for the key, or None when adding a new key.
        is_new (bool): True when adding a new key; affects prompts and suggested defaults.
        section_name (str): Section name used to look up a suggested default for new keys.

    Returns:
        Optional[Any]: The value coerced from the user's input, or `None` if the prompt was cancelled.
    """
    console.print()
    display_key = key.replace(".", " › ")

    if is_new:
        console.print(f"Add [{get_accent_style()}]{display_key}[/{get_accent_style()}]")

        # Get default from schema if available
        schema = _get_available_config_schema()
        default_value = schema.get(section_name, {}).get(key)

        if default_value is not None:
            formatted_default = _format_config_value(default_value)
            console.print(
                f"Suggested value: [{get_secondary_style()}]{formatted_default}[/{get_secondary_style()}]"
            )
        console.print()

        # Convert default to string
        default_str = _value_to_default_str(default_value)
    else:
        console.print(
            f"Update [{get_accent_style()}]{display_key}[/{get_accent_style()}]"
        )
        formatted_current = _format_config_value(current_value)
        console.print(
            f"Current value: [{get_secondary_style()}]{formatted_current}[/{get_secondary_style()}]"
        )
        console.print()

        # Convert current value to string for default
        default_str = _value_to_default_str(current_value)

    prompt_text = (
        "Value (or press Enter to cancel)"
        if is_new
        else "New value (or press Enter to cancel)"
    )
    new_value_str = typer.prompt(
        prompt_text, default=default_str, show_default=bool(default_str)
    )

    # If user just pressed Enter with empty default, cancel
    if not new_value_str and not default_str:
        return None

    # Coerce the value
    return _coerce_value(new_value_str)


def _preview_change(
    key: str, old_value: Any, new_value: Any, is_new: bool = False
) -> None:
    """
    Show a UI preview card for a pending configuration change.

    Displays a detail card that summarizes the change for the given configuration `key`.
    If `is_new` is True, the card indicates an "Add new value" action and shows the formatted
    new value. Otherwise the card shows the formatted current value and the formatted new value,
    with the title set to "Update Configuration" for updates and "Add Configuration" for additions.

    Parameters:
        key (str): Dot-path configuration key being changed.
        old_value (Any): Existing value for the key; may be None for new keys.
        new_value (Any): Proposed new value to display.
        is_new (bool): If True, treat the change as adding a new key (default False).
    """
    console.print()
    console.print(f"[{get_heading_style()}]Preview Change[/{get_heading_style()}]")
    console.print()

    rows = [("Key", key)]

    if is_new:
        rows.append(("Action", "Add new value"))
        rows.append(("Value", _format_config_value(new_value)))
        title = "Add Configuration"
    else:
        rows.append(("Current", _format_config_value(old_value)))
        rows.append(("New", _format_config_value(new_value)))
        title = "Update Configuration"

    card = create_detail_card(title=title, rows=rows)
    console.print(card)
    console.print()


def _load_external_toml(file_path: str) -> Optional[dict[str, Any]]:
    """
    Parse a TOML file at the provided filesystem path and return its contents as a dictionary.

    Parameters:
        file_path (str): Filesystem path to the TOML file; can be relative or absolute.

    Returns:
        dict: Parsed TOML data when successful.
        None: If the file does not exist, is not a regular file, a TOML parser is unavailable, or parsing fails. Errors are reported to the user before returning None.
    """
    import sys

    # TOML read (tomllib on 3.11+, fallback to tomli)
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib
        except ImportError:
            print_error("TOML library not available")
            return None

    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        print_error(f"File not found: {path}")
        return None

    if not path.is_file():
        print_error(f"Not a file: {path}")
        return None

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return data
    except Exception as e:
        print_error(f"Failed to parse TOML: {e}")
        return None


def _backup_config(config_path: Path) -> bool:
    """Create a backup of the current config file.

    Args:
        config_path: Path to config file

    Returns:
        True if backup created successfully, False otherwise
    """
    import shutil
    from datetime import datetime

    if not config_path.exists():
        return True  # Nothing to backup

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.parent / f"config.toml.backup.{timestamp}"

    try:
        shutil.copy2(config_path, backup_path)
        print_success(f"Backup created: {backup_path.name}")
        return True
    except Exception as e:
        print_warning(f"Could not create backup: {e}")
        return False


def _show_config_diff(current: dict[str, Any], new: dict[str, Any]) -> None:
    """Show differences between current and new config.

    Args:
        current: Current configuration
        new: New configuration
    """
    console.print()
    console.print(
        f"[{get_heading_style()}]Configuration Changes[/{get_heading_style()}]"
    )
    console.print()

    current_flat = _flatten_dict(current)
    new_flat = _flatten_dict(new)

    all_keys = set(current_flat.keys()) | set(new_flat.keys())

    added = []
    removed = []
    modified = []

    for key in sorted(all_keys):
        if key not in current_flat:
            added.append((key, new_flat[key]))
        elif key not in new_flat:
            removed.append((key, current_flat[key]))
        elif current_flat[key] != new_flat[key]:
            modified.append((key, current_flat[key], new_flat[key]))

    if added:
        console.print(f"[{get_success_style()}]Added:[/{get_success_style()}]")
        for key, value in added:
            console.print(f"  + {key}: {_format_config_value(value)}")
        console.print()

    if removed:
        console.print(f"[{get_error_style()}]Removed:[/{get_error_style()}]")
        for key, value in removed:
            console.print(f"  - {key}: {_format_config_value(value)}")
        console.print()

    if modified:
        console.print(f"[{get_warning_style()}]Modified:[/{get_warning_style()}]")
        for key, old_val, new_val in modified:
            console.print(f"  ~ {key}:")
            console.print(
                f"    [{get_secondary_style()}]Old:[/{get_secondary_style()}] {_format_config_value(old_val)}"
            )
            console.print(
                f"    [{get_accent_style()}]New:[/{get_accent_style()}] {_format_config_value(new_val)}"
            )
        console.print()

    if not added and not removed and not modified:
        console.print(
            f"[{get_secondary_style()}]No changes detected[/{get_secondary_style()}]"
        )
        console.print()


# ============================================================================
# Commands
# ============================================================================


@app.command("inspect")
def inspect(
    section: Optional[str] = typer.Argument(
        None,
        help="Section to inspect (sources, core, logging, mcp, performance)",
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
):
    """Display merged configuration (global + workspace + env).

    Examples:
        indexed config inspect          # Show custom values + select defaults
        indexed config inspect sources  # Show only sources config
        indexed config inspect --defaults  # Show all values including defaults
    """
    from ..utils.logging import setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)

    config = ConfigService.instance()
    raw = config.load_raw()

    from ..utils.simple_output import is_simple_output, print_json

    if is_simple_output():
        print_json(raw)
        return

    # Normalize section argument
    section_filter = section.lower() if section else None

    console.print()
    if section_filter:
        console.print(
            f"[{get_heading_style()}]Configuration: {section_filter.title()}[/{get_heading_style()}]"
        )
    else:
        console.print(
            f"[{get_heading_style()}]Configuration Overview[/{get_heading_style()}]"
        )
    console.print()

    # Get defaults schema and merge with raw config
    defaults_schema = _get_full_config_schema()
    merged = _merge_with_defaults(raw, defaults_schema)

    # Track statistics
    manual_keys = 0
    default_keys = 0
    manual_sections: set[str] = set()

    # Select default values to always show (when not showing all defaults)
    SELECT_DEFAULTS = {
        ("core", "v1.embedding.model_name"),
        ("core", "v1.embedding.provider"),
        ("core", "v1.storage.type"),
        ("logging", "level"),
    }

    # Group sections by type for display
    sources_sections = {}
    core_sections = {}
    other_sections = {}

    for section_name, section_data in merged.items():
        if not section_data:
            continue

        # Categorize sections
        if section_name == "sources":
            sources_sections[section_name] = section_data
        elif section_name == "core":
            core_sections[section_name] = section_data
        else:
            other_sections[section_name] = section_data

        # Count keys
        for key, info in section_data.items():
            if info["is_default"]:
                default_keys += 1
            else:
                manual_keys += 1
                manual_sections.add(section_name)

    # Get workspace config separately
    workspace_config = config.get_workspace_config()

    # Helper to check if a key should be shown
    def should_show_key(section: str, key: str, is_default: bool) -> bool:
        """
        Decides whether a configuration key should be displayed.

        A key is shown if it is a manually set value, or if default values are globally enabled for display, or if the (section, key) pair is included in the predefined selected-defaults set.

        Parameters:
            section (str): Top-level configuration section name.
            key (str): Configuration key path (relative to the section).
            is_default (bool): True when the key's value originates from defaults, False when manually set.

        Returns:
            bool: `true` if the key should be shown, `false` otherwise.
        """
        if not is_default:
            return True  # Always show manual values
        if show_defaults:
            return True  # Show all if --show-defaults
        # Check if it's a select default
        return (section, key) in SELECT_DEFAULTS

    # Display Sources panel (if no filter or filter matches)
    if sources_sections and (not section_filter or section_filter == "sources"):
        rows: list[tuple[str, str, str]] = []
        for section_name, section_data in sources_sections.items():
            for key, info in sorted(section_data.items()):
                if should_show_key(section_name, key, info["is_default"]):
                    # Split key to get category (e.g., "confluence.query" -> "confluence", "query")
                    parts = key.split(".", 1)
                    category = parts[0] if len(parts) > 1 else section_name
                    subkey = parts[1] if len(parts) > 1 else key
                    value = _format_config_value(info["value"])
                    rows.append((category, subkey, value))

        if rows:
            panel = create_key_value_panel(
                "Sources",
                rows,
                category_width=14,
                key_width=20,
                headers=("source", "setting", "value"),
            )
            console.print(panel)
            console.print()

    # Display Core Settings panel (if showing defaults or filter matches)
    if core_sections and (show_defaults or section_filter == "core"):
        rows = []
        for section_name, section_data in core_sections.items():
            for key, info in sorted(section_data.items()):
                if should_show_key(section_name, key, info["is_default"]):
                    # Key format: "v1.indexing.chunk_size" -> category="indexing", subkey="chunk_size"
                    parts = key.split(".")
                    if len(parts) >= 2:
                        category = parts[-2] if len(parts) > 2 else parts[0]
                        subkey = parts[-1]
                    else:
                        category = "core"
                        subkey = key
                    value = _format_config_value(info["value"])
                    rows.append((category, subkey, value))

        if rows:
            panel = create_key_value_panel(
                "Core Settings",
                rows,
                category_width=14,
                key_width=24,
                headers=("category", "setting", "value"),
            )
            console.print(panel)
            console.print()

    # Display other sections (logging, mcp, performance)
    for section_name, section_data in sorted(other_sections.items()):
        # Skip if filtering and doesn't match
        if section_filter and section_filter != section_name:
            continue

        rows = []
        for key, info in sorted(section_data.items()):
            if should_show_key(section_name, key, info["is_default"]):
                value = _format_config_value(info["value"])
                rows.append((section_name, key, value))

        if rows and show_defaults:
            title = section_name.replace("_", " ").title()
            panel = create_key_value_panel(
                title,
                rows,
                category_width=14,
                key_width=24,
                headers=("category", "setting", "value"),
            )
            console.print(panel)
            console.print()

    # Display Workspace panel (if no filter)
    if workspace_config and not section_filter:
        ws_rows: list[tuple[str, str]] = []

        # Mode
        ws_rows.append(("mode", workspace_config.get("mode", "")))

        # Local path (truncate if needed)
        local_path = workspace_config.get("local_path", "")
        if len(local_path) > 45:
            local_path = "..." + local_path[-42:]
        ws_rows.append(("local_path", local_path))

        # Global path (truncate if needed)
        global_path = workspace_config.get("global_path", "~/.indexed")
        if len(global_path) > 45:
            global_path = "..." + global_path[-42:]
        ws_rows.append(("global_path", global_path))

        panel = create_simple_key_value_panel(
            "Workspace",
            ws_rows,
            key_width=15,
            value_max_len=50,
            headers=("setting", "value"),
        )
        console.print(panel)
        console.print()

    # Display Select Default Values panel (only when not filtering and not showing all defaults)
    if not section_filter and not show_defaults:
        select_rows: list[tuple[str, str, str]] = []

        # Collect select default values
        for section_name, section_data in merged.items():
            for key, info in sorted(section_data.items()):
                if (section_name, key) in SELECT_DEFAULTS and info["is_default"]:
                    # Parse key for display
                    parts = key.split(".")
                    if len(parts) >= 2:
                        category = parts[-2] if len(parts) > 2 else parts[0]
                        subkey = parts[-1]
                    else:
                        category = section_name
                        subkey = key
                    value = _format_config_value(info["value"])
                    select_rows.append((category, subkey, value))

        if select_rows:
            panel = create_key_value_panel(
                "Select Default Values",
                select_rows,
                category_width=14,
                key_width=24,
                headers=("category", "setting", "value"),
            )
            console.print(panel)
            # Count remaining defaults
            remaining_defaults = default_keys - len(select_rows)
            if remaining_defaults > 0:
                console.print(
                    f"[{get_secondary_style()}]{remaining_defaults} more default values used...[/{get_secondary_style()}]"
                )
            console.print()

    # Summary with manual vs default statistics
    total_keys = manual_keys + default_keys
    if total_keys == 0 and not workspace_config:
        console.print(f"[{get_dim_style()}]No configuration found[/{get_dim_style()}]")
        console.print()
        return

    # Build informative summary
    if manual_keys > 0:
        section_list = ", ".join(sorted(manual_sections))
        heading = get_heading_style()
        console.print(
            f"[{heading}]Overall:[/{heading}] [{get_accent_style()}]{manual_keys}[/{get_accent_style()}] keys "
            f"set manually for [{get_accent_style()}]{section_list}[/{get_accent_style()}]."
        )
    elif workspace_config:
        mode = workspace_config.get("mode", "unknown")
        heading = get_heading_style()
        console.print(
            f"[{heading}]Overall:[/{heading}] Workspace configured in [{get_accent_style()}]{mode}[/{get_accent_style()}] mode"
        )
    else:
        heading = get_heading_style()
        console.print(f"[{heading}]Overall:[/{heading}] All values using defaults")
    console.print()


@app.command("update")
def update(
    file: Optional[str] = typer.Option(
        None, "--file", "-f", help="Path to TOML file to replace global configuration"
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
):
    """Update global configuration interactively or from file."""
    from ..utils.logging import setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)

    config = ConfigService.instance()
    global_path = config._store.global_path

    # If --file flag is provided, go directly to file replacement
    if file:
        _handle_file_replace_with_path(config, global_path, file)
        return

    # Default: Interactive individual settings update
    while True:
        result = _handle_individual_update(config, global_path)
        if not result:
            # User wants to exit
            console.print()
            console.print(
                f"[{get_secondary_style()}]Exiting configuration update.[/{get_secondary_style()}]"
            )
            console.print()
            break


def _handle_individual_update(config: ConfigService, global_path: Path) -> bool:
    """
    Run an interactive flow to add or update a single configuration key in the global configuration.

    Prompts the user to select a section and key, collect a new value (with coercion), preview the change, and on confirmation persist the update to the global config file.

    Parameters:
        config (ConfigService): Service used to read, validate, and write configuration.
        global_path (Path): Path to the global configuration TOML file to be updated.

    Returns:
        bool: `True` to continue the interactive update loop, `False` to exit.

    Raises:
        typer.Exit: If applying the change fails when writing the global configuration.
    """
    # Load current config
    current_config = config.load_raw()

    if not current_config:
        current_config = {}

    # Group by sections
    grouped = _group_config_by_section(current_config)

    # Select section (shows both existing and available sections)
    section_name = _select_section(grouped)
    if not section_name:
        return False  # User wants to exit

    # Get section data (empty dict if section doesn't exist yet)
    section_data = grouped.get(section_name, {})

    # Select key (returns tuple of (key, is_new))
    result = _select_key(section_name, section_data)
    if not result:
        return True  # Go back to section selection

    key, is_new = result

    # Build full dot-path key
    full_key = f"{section_name}.{key}"
    current_value = section_data.get(key) if not is_new else None

    # Prompt for new value
    new_value = _prompt_for_value(
        full_key, current_value, is_new=is_new, section_name=section_name
    )
    if new_value is None:
        console.print()
        console.print(f"[{get_secondary_style()}]Cancelled[/{get_secondary_style()}]")
        console.print()
        return True

    # Preview change
    _preview_change(full_key, current_value, new_value, is_new=is_new)

    # Confirm
    action_text = "Add this configuration?" if is_new else "Apply this change?"
    if not typer.confirm(action_text, default=True):
        console.print()
        console.print(f"[{get_secondary_style()}]Cancelled[/{get_secondary_style()}]")
        console.print()
        return True

    # Apply change to global config only
    try:
        # Read global config directly (not merged)
        global_config = (
            config._store._read_toml_file(global_path) if global_path.exists() else {}
        )

        # Set the value in global config
        set_by_path(global_config, full_key, new_value)

        # Ensure directory exists
        global_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to global config
        config._store.write(global_config)

        console.print()
        success_msg = "added" if is_new else "updated"
        print_success(f"Configuration {success_msg} successfully")
        console.print(
            f"[{get_secondary_style()}]Location: {global_path}[/{get_secondary_style()}]"
        )
        console.print()

    except Exception as e:
        console.print()
        print_error(f"Error updating configuration: {e}")
        raise typer.Exit(1)

    return True


def _handle_file_replace_with_path(
    config: ConfigService, global_path: Path, file_path: str
) -> bool:
    """
    Replace the global configuration file with the contents of a TOML file after interactive confirmation.

    Loads and parses the provided TOML file, displays a diff against the current global configuration, validates the new configuration by temporarily writing it to the config store, prompts the user for confirmation, creates a backup of the existing global file, and writes the new configuration to the global path if confirmed.

    Parameters:
        config (ConfigService): Configuration service used for temporary write and validation.
        global_path (Path): Path to the global configuration file to be replaced.
        file_path (str): Filesystem path to the TOML file to load and apply.

    Returns:
        bool: `True` if the replacement completed successfully, `False` if the operation was cancelled or validation/loading failed.

    Raises:
        typer.Exit: If writing the new configuration to the global path fails.
    """
    console.print()
    console.print(
        f"[{get_heading_style()}]Replace Configuration From File[/{get_heading_style()}]"
    )
    console.print()
    print_warning("This will completely replace your global configuration!")
    console.print()

    # Load and validate the file
    new_config = _load_external_toml(file_path)
    if new_config is None:
        console.print()
        return False

    console.print()
    print_success("TOML file loaded successfully")
    console.print()

    # Show what will change
    current_config = (
        config._store._read_toml_file(global_path) if global_path.exists() else {}
    )
    _show_config_diff(current_config, new_config)

    # Validate the new config in-memory without writing
    console.print(
        f"[{get_heading_style()}]Validating Configuration...[/{get_heading_style()}]"
    )
    console.print()

    try:
        # Validate in-memory by creating a temporary ConfigService
        # that uses the new_config dict instead of reading from files
        from indexed_config.path_utils import get_by_path
        from pydantic import ValidationError

        # Create a temporary config service for validation
        temp_config = ConfigService.instance()

        # Get all registered specs
        registered_specs = temp_config._specs.copy()

        # Validate against new_config dict directly
        errors = []
        for path, spec in registered_specs.items():
            payload = get_by_path(new_config, path, default=None)
            # Only validate sections that exist (skip absent optional sections)
            if payload in (None, {}):
                continue
            try:
                spec.model_validate(payload)  # type: ignore[arg-type]
            except ValidationError as exc:
                errors.append((path, str(exc)))

        if errors:
            print_error("Validation failed")
            console.print()
            for path, msg in errors:
                console.print(f"  • {path}: {msg}")
            console.print()
            console.print(
                f"[{get_secondary_style()}]Fix these errors in the TOML file and try again.[/{get_secondary_style()}]"
            )
            console.print()
            return False

        print_success("Configuration is valid")
        console.print()

    except Exception as e:
        print_error(f"Validation error: {e}")
        return False

    # Final confirmation
    print_warning(f"This will replace your global configuration at: {global_path}")
    console.print()

    if not typer.confirm("Continue with replacement?", default=False):
        console.print()
        console.print(f"[{get_secondary_style()}]Cancelled[/{get_secondary_style()}]")
        console.print()
        return False

    # Create backup
    console.print()
    if not _backup_config(global_path):
        if not typer.confirm("Continue without backup?", default=False):
            console.print(
                f"[{get_secondary_style()}]Cancelled[/{get_secondary_style()}]"
            )
            console.print()
            return False

    # Write new config to global path
    try:
        global_path.parent.mkdir(parents=True, exist_ok=True)

        import tomlkit

        with open(global_path, "w", encoding="utf-8") as f:
            tomlkit.dump(new_config, f)

        console.print()
        print_success("Global configuration replaced successfully")
        console.print(
            f"[{get_secondary_style()}]Location: {global_path}[/{get_secondary_style()}]"
        )
        console.print()

    except Exception as e:
        console.print()
        print_error(f"Error writing configuration: {e}")
        raise typer.Exit(1)

    return True


@app.command("set")
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
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        rich_help_panel="Logging",
    ),
):
    """Set a configuration value at dot-path in workspace config."""
    from ..utils.logging import setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)

    config = ConfigService.instance()
    coerced = _coerce_value(value)

    # Get old value if exists
    try:
        old_raw = config.load_raw() or {}
        from indexed_config.path_utils import get_by_path

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
            rows.append(("Previous", _format_config_value(old_value)))
        rows.append(("New", _format_config_value(coerced)))

        card = create_detail_card(title="Change Summary", rows=rows)
        console.print(card)
        console.print()
        console.print(
            f"[{get_secondary_style()}]Preview only - not saved (remove --dry-run to save)[/{get_secondary_style()}]"
        )
        console.print()
        return

    try:
        config.set(key, coerced)

        # Validate
        errs = config.validate()
        if errs:
            console.print()
            print_warning("Validation warnings detected")
            console.print()
            for path, msg in errs:
                console.print(
                    f"  [{get_warning_style()}]•[/{get_warning_style()}] {path}: {msg}"
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
            rows.append(("Previous", _format_config_value(old_value)))
        rows.append(("New", _format_config_value(coerced)))

        card = create_detail_card(title="Change Summary", rows=rows)
        console.print(card)
        console.print()
        print_success("Configuration saved to .indexed/config.toml")
        console.print()

    except Exception as e:
        console.print()
        print_error(f"Error: {e}")
        raise typer.Exit(1)


@app.command("delete")
def delete_config(
    key: str = typer.Argument(..., help="Dot path to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
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
):
    """
    Delete a configuration key from the workspace configuration.

    Shows the current value and, unless `force` is True, prompts for confirmation before removing the key from the workspace config. Reports success when the key is deleted and prints informational messages if the key is not found.

    Parameters:
        key (str): Dot-separated path of the configuration key to delete (e.g., "core.v1.indexing.chunk_size").
        force (bool): If True, skip the confirmation prompt and delete immediately.
        verbose (bool): Enable verbose (INFO) logging.
        json_logs (bool): Output logs as JSON (structured).
        log_level (Optional[str]): Explicit logging level (e.g., "DEBUG", "INFO", "WARNING", "ERROR").
    """
    from ..utils.logging import setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)

    config = ConfigService.instance()

    # Get current value
    try:
        raw = config.load_raw() or {}
        current_value = raw
        for part in key.split("."):
            if isinstance(current_value, dict):
                current_value = current_value.get(part)
            else:
                current_value = None
                break
    except Exception:
        current_value = None

    if current_value is None:
        console.print()
        print_info(f"Key not found: {key}")
        console.print()
        return

    # Show confirmation prompt
    if not force:
        console.print()
        console.print(
            f"[{get_heading_style()}]Delete Configuration Key[/{get_heading_style()}]"
        )
        console.print()

        rows = [
            ("Key", key),
            ("Value", _format_config_value(current_value)),
        ]

        card = create_detail_card(title="Current Value", rows=rows)
        console.print(card)
        console.print()
        print_warning("This will remove the key from workspace config.")

        if not typer.confirm("Continue?", default=False):
            console.print(
                f"[{get_secondary_style()}]Cancelled[/{get_secondary_style()}]"
            )
            console.print()
            return

    # Delete the key
    if config.delete(key):
        console.print()
        print_success(f"Deleted {key}")
        console.print()
    else:
        console.print()
        print_info(f"Key not found: {key}")
        console.print()


@app.command("validate")
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
):
    """
    Validate the active configuration against registered validation rules and report any problems.

    Runs configuration validation, prints a success message when no issues are found, and prints grouped, sectioned error cards when issues exist. If validation errors are present the command prints a summary and exits the process with status code 1.
    """
    from ..utils.logging import setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)

    config = ConfigService.instance()
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
            # Show path and message
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


@app.command("init")
def init_config(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing config files"
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
):
    """
    Initialize workspace configuration files by creating a .indexed directory with a default config.toml and .env.example.

    If the workspace already exists and `force` is False, the command exits without modifying files. When `force` is True, existing files are overwritten. Logging options control logging level and JSON formatting for the command's output.

    Parameters:
        force (bool): Overwrite existing configuration files when True.
        verbose (bool): Enable verbose (INFO) logging.
        json_logs (bool): Emit logs in JSON (structured) format.
        log_level (Optional[str]): Explicit logging level (e.g., "DEBUG", "INFO"); overrides `verbose` when provided.
    """
    from ..utils.logging import setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)

    workspace_dir = Path.cwd() / ".indexed"
    config_file = workspace_dir / "config.toml"
    env_example = workspace_dir / ".env.example"

    console.print()
    console.print(f"[{get_heading_style()}]Config › Initialize[/{get_heading_style()}]")
    console.print()

    # Check if already initialized
    if workspace_dir.exists() and not force:
        print_warning(f"Workspace already initialized at {workspace_dir}")
        console.print()
        console.print(
            f"[{get_secondary_style()}]Use --force to overwrite existing configuration.[/{get_secondary_style()}]"
        )
        console.print()
        raise typer.Exit(1)

    # Create directory
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Default config.toml content
    default_config = """# Indexed Configuration
# See: https://indexed.ignitr.dev/docs/configuration

[core.v1.indexing]
chunk_size = 512
chunk_overlap = 50

[core.v1.embedding]
model_name = "all-MiniLM-L6-v2"

[core.v1.search]
max_docs = 10
max_chunks = 50
# score_threshold = 0.0  # Optional: minimum similarity score

# Storage paths are automatically resolved:
# - Global: ~/.indexed/data/collections (default)
# - Local: ./.indexed/data/collections (when --local flag is used)
# Uncomment below to override:
# [core.v1.storage]
# base_path = "~/.indexed/data/collections"

# Source configurations
# Uncomment and configure the sources you need

# [sources.files]
# path = "./docs"
# include_patterns = [".*\\\\.md$", ".*\\\\.txt$"]
# exclude_patterns = []
# fail_fast = false

# [sources.jira]
# url = "https://company.atlassian.net"
# query = "project = PROJ"
# email = ""  # Set via ATLASSIAN_EMAIL env var
# api_token = ""  # Set via ATLASSIAN_TOKEN env var

# [sources.confluence]
# url = "https://company.atlassian.net/wiki"
# query = "space = DOCS"
# email = ""  # Set via ATLASSIAN_EMAIL env var
# api_token = ""  # Set via ATLASSIAN_TOKEN env var
# read_all_comments = true
"""

    # .env.example content
    env_example_content = """# Indexed Environment Variables
# Copy this file to .env and fill in your values

# Atlassian Cloud (Jira Cloud, Confluence Cloud)
# ATLASSIAN_EMAIL=your-email@company.com
# ATLASSIAN_TOKEN=your-api-token

# Jira Server/Data Center
# JIRA_TOKEN=your-jira-token
# JIRA_LOGIN=your-username
# JIRA_PASSWORD=your-password

# Confluence Server/Data Center
# CONF_TOKEN=your-confluence-token
# CONF_LOGIN=your-username
# CONF_PASSWORD=your-password
"""

    files_created = []
    files_skipped = []

    # Write config.toml
    if not config_file.exists() or force:
        config_file.write_text(default_config)
        files_created.append(str(config_file))
    else:
        files_skipped.append(str(config_file))

    # Write .env.example
    if not env_example.exists() or force:
        env_example.write_text(env_example_content)
        files_created.append(str(env_example))
    else:
        files_skipped.append(str(env_example))

    # Show results
    if files_created:
        rows = [(Path(f).name, "created") for f in files_created]
        if files_skipped:
            rows.extend([(Path(f).name, "skipped (exists)") for f in files_skipped])

        card = create_info_card(title="Initialization Complete", rows=rows)
        console.print(card)
        console.print()

    print_success(f"Workspace initialized at {workspace_dir}")
    console.print()

    # Next steps
    console.print(f"[{get_heading_style()}]Next Steps:[/{get_heading_style()}]")
    console.print()
    console.print(
        f"  1. Edit [{get_accent_style()}]{config_file}[/{get_accent_style()}] to configure your sources"
    )
    console.print(
        f"  2. Copy [{get_accent_style()}]{env_example}[/{get_accent_style()}] to [{get_accent_style()}].env[/{get_accent_style()}] and add your credentials"
    )
    console.print(
        f"  3. Run [{get_accent_style()}]indexed config validate[/{get_accent_style()}] to verify configuration"
    )
    console.print()


@app.command("docs", rich_help_panel="Resources")
def docs() -> None:
    """Open configuration documentation in browser."""
    url = "https://indexed.ignitr.dev/docs/configuration"
    try:
        webbrowser.open(url)
        console.print()
        print_success("Opening configuration documentation in browser...")
        console.print(f"[{get_secondary_style()}]{url}[/{get_secondary_style()}]")
        console.print()
    except Exception as e:
        console.print()
        print_error(f"Failed to open browser: {e}")
        console.print(f"Visit manually: {url}")
        console.print()
        raise typer.Exit(1)
