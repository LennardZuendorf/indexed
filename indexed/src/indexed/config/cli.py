"""Config command for managing index configuration."""

import json
from typing import Any, Optional
from collections import defaultdict

import typer
from rich.panel import Panel
from rich.console import Group
from rich.columns import Columns
from rich.text import Text

from indexed_config import ConfigService
from ..utils.console import console
from ..utils.components import (
    create_info_card,
    create_detail_card,
    create_summary,
    get_card_padding,
    get_heading_style,
    get_success_style,
    get_error_style,
    get_warning_style,
    get_secondary_style,
    get_accent_style,
)

app = typer.Typer(help="Manage configuration")


# ============================================================================
# Helper Functions
# ============================================================================


def _coerce_value(value: str) -> Any:
    """Coerce string value to appropriate type.
    
    Args:
        value: String value to coerce
        
    Returns:
        Coerced value (int, float, bool, list, dict, or string)
    """
    # Try int, float, bool, JSON (list/dict), else keep string
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return int(value)
        f = float(value)
        return f
    except Exception:
        pass
    try:
        return json.loads(value)
    except Exception:
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
    """Group configuration by top-level sections.
    
    Args:
        config_dict: Configuration dictionary
        
    Returns:
        Dictionary grouped by section name
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
    """Format a config value for display.
    
    Args:
        value: Value to format
        
    Returns:
        Formatted string
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


def _create_section_card(section_name: str, section_data: dict[str, Any]) -> Panel:
    """Create a card for a config section.
    
    Args:
        section_name: Name of the section
        section_data: Configuration data for the section
        
    Returns:
        Panel with section data
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


# ============================================================================
# Commands
# ============================================================================


@app.command("inspect")
def inspect(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Display merged configuration (global + workspace + env)."""
    config = ConfigService()
    raw = config.load_raw()
    
    if json_output:
        console.print(json.dumps(raw, indent=2, ensure_ascii=False))
        return
    
    console.print()
    console.print(f"[{get_heading_style()}]Configuration Overview[/{get_heading_style()}]")
    console.print()
    
    # Group config by sections
    grouped = _group_config_by_section(raw)
    
    if not grouped:
        console.print("[dim]No configuration found[/dim]")
        console.print()
        return
    
    # Create cards for each section
    cards = []
    total_keys = 0
    
    for section_name in sorted(grouped.keys()):
        section_data = grouped[section_name]
        total_keys += len(section_data)
        card = _create_section_card(section_name, section_data)
        cards.append(card)
    
    # Display cards in columns (2-3 per row)
    if len(cards) > 1:
        console.print(Columns(cards, equal=True, expand=True))
    else:
        console.print(cards[0])
    
    # Summary
    console.print()
    section_count = len(grouped)
    plural = "section" if section_count == 1 else "sections"
    console.print(
        create_summary(
            "Total",
            f"{section_count} {plural}, {total_keys} keys configured"
        )
    )
    console.print()


@app.command("init")
def init(
    yes: bool = typer.Option(False, "--yes", "-y", help="Use defaults without prompting")
):
    """Initialize workspace configuration with interactive setup."""
    console.print()
    console.print(f"[{get_heading_style()}]🚀 Initialize Indexed Configuration[/{get_heading_style()}]")
    console.print()
    console.print("Set up your local document search configuration.")
    console.print()
    
    config_values = {}
    
    if yes:
        # Non-interactive mode - use defaults
        config = ConfigService()
        raw = config.load_raw()
        config.save_raw(raw or {})
        console.print(f"[{get_success_style()}]✓ Workspace configuration initialized with defaults[/{get_success_style()}]")
        console.print(f"[{get_secondary_style()}]Location: .indexed/config.toml[/{get_secondary_style()}]")
        console.print()
        return
    
    # Interactive mode - prompt for essential settings
    console.print(f"[{get_accent_style()}]Essential Settings[/{get_accent_style()}]")
    console.print()
    
    # Chunk size
    chunk_size = typer.prompt(
        "Chunk size for document splitting",
        default=512,
        type=int
    )
    config_values["core"] = {"v1": {"indexing": {"chunk_size": chunk_size}}}
    
    # Embedding model
    embedding_model = typer.prompt(
        "Embedding model",
        default="all-MiniLM-L6-v2"
    )
    config_values["embedding"] = {"model": embedding_model}
    
    console.print()
    
    # Connector setup
    if typer.confirm("Would you like to configure connectors?", default=True):
        console.print()
        console.print(f"[{get_accent_style()}]Connector Setup[/{get_accent_style()}]")
        console.print()
        
        connectors_config = {}
        
        while True:
            console.print("Available connectors:")
            console.print("  1. Jira Cloud")
            console.print("  2. Confluence Cloud")
            console.print("  3. Local Files")
            console.print("  4. Done (skip remaining)")
            console.print()
            
            choice = typer.prompt("Select connector", default="4")
            
            if choice == "4" or choice.lower() == "done":
                break
            elif choice == "1":
                # Jira Cloud
                console.print()
                console.print("[dim]Jira Cloud Configuration[/dim]")
                jira_url = typer.prompt("Jira URL (e.g., https://company.atlassian.net)")
                jira_email = typer.prompt("Email")
                jira_query = typer.prompt("JQL Query", default="project = PROJ")
                connectors_config["jira"] = {
                    "url": jira_url,
                    "email": jira_email,
                    "query": jira_query
                }
                console.print(f"[{get_success_style()}]✓ Jira Cloud configured[/{get_success_style()}]")
                console.print()
            elif choice == "2":
                # Confluence Cloud
                console.print()
                console.print("[dim]Confluence Cloud Configuration[/dim]")
                conf_url = typer.prompt("Confluence URL (e.g., https://company.atlassian.net/wiki)")
                conf_email = typer.prompt("Email")
                conf_query = typer.prompt("CQL Query", default="space = DEV")
                read_comments = typer.confirm("Read all comments?", default=False)
                connectors_config["confluence"] = {
                    "url": conf_url,
                    "email": conf_email,
                    "query": conf_query,
                    "read_all_comments": read_comments
                }
                console.print(f"[{get_success_style()}]✓ Confluence Cloud configured[/{get_success_style()}]")
                console.print()
            elif choice == "3":
                # Local Files
                console.print()
                console.print("[dim]Local Files Configuration[/dim]")
                file_path = typer.prompt("Base path", default="./documents")
                include_patterns = typer.prompt("Include patterns (comma-separated)", default="*.md,*.txt")
                patterns_list = [p.strip() for p in include_patterns.split(",")]
                connectors_config["files"] = {
                    "path": file_path,
                    "include_patterns": patterns_list
                }
                console.print(f"[{get_success_style()}]✓ Local Files configured[/{get_success_style()}]")
                console.print()
            else:
                console.print("[dim]Invalid choice, please try again[/dim]")
                console.print()
        
        if connectors_config:
            config_values["connectors"] = connectors_config
    
    console.print()
    
    # Advanced settings
    if typer.confirm("Configure advanced settings?", default=False):
        console.print()
        console.print(f"[{get_accent_style()}]Advanced Settings[/{get_accent_style()}]")
        console.print()
        
        chunk_overlap = typer.prompt("Chunk overlap", default=50, type=int)
        batch_size = typer.prompt("Batch size", default=32, type=int)
        
        if "core" not in config_values:
            config_values["core"] = {"v1": {"indexing": {}}}
        config_values["core"]["v1"]["indexing"]["chunk_overlap"] = chunk_overlap
        config_values["core"]["v1"]["indexing"]["batch_size"] = batch_size
        console.print()
    
    # Show summary
    console.print(f"[{get_heading_style()}]Configuration Summary[/{get_heading_style()}]")
    console.print()
    
    # Group by section for better organization
    grouped = _group_config_by_section(config_values)
    
    cards = []
    for section_name in sorted(grouped.keys()):
        section_data = grouped[section_name]
        card = _create_section_card(section_name, section_data)
        cards.append(card)
    
    if len(cards) > 1:
        console.print(Columns(cards, equal=True, expand=True))
    else:
        console.print(cards[0])
    
    console.print()
    
    # Confirmation
    if not typer.confirm("Save configuration?", default=True):
        console.print("[dim]Configuration not saved[/dim]")
        console.print()
        return
    
    # Save configuration
    config = ConfigService()
    
    # Merge with existing config
    existing = config.load_raw() or {}
    
    # Deep merge the configs
    def deep_merge(base: dict, updates: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    merged = deep_merge(existing, config_values)
    config.save_raw(merged)
    
    console.print(f"[{get_success_style()}]✓ Workspace configuration initialized[/{get_success_style()}]")
    console.print(f"[{get_secondary_style()}]Location: .indexed/config.toml[/{get_secondary_style()}]")
    console.print()


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Dot path (e.g., core.v1.indexing.chunk_size)"),
    value: str = typer.Argument(..., help="Value (auto-coerced)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview change without saving"),
):
    """Set a configuration value at dot-path in workspace config."""
    config = ConfigService()
    coerced = _coerce_value(value)
    
    # Get old value if exists
    try:
        old_raw = config.load_raw() or {}
        old_value = old_raw
        for part in key.split("."):
            if isinstance(old_value, dict):
                old_value = old_value.get(part)
            else:
                old_value = None
                break
    except Exception:
        old_value = None
    
    if dry_run:
        # Preview mode
        console.print()
        console.print(f"[{get_heading_style()}]Configuration Preview[/{get_heading_style()}]")
        console.print()
        
        rows = [("Key", key)]
        if old_value is not None:
            rows.append(("Previous", _format_config_value(old_value)))
        rows.append(("New", _format_config_value(coerced)))
        
        card = create_detail_card(title="Change Summary", rows=rows)
        console.print(card)
        console.print()
        console.print(f"[{get_secondary_style()}]Preview only - not saved (remove --dry-run to save)[/{get_secondary_style()}]")
        console.print()
        return
    
    try:
        config.set(key, coerced)
        
        # Validate
        errs = config.validate()
        if errs:
            console.print()
            console.print(f"[{get_warning_style()}]⚠️  Validation warnings detected:[/{get_warning_style()}]")
            console.print()
            for path, msg in errs:
                console.print(f"  [{get_warning_style()}]•[/{get_warning_style()}] {path}: {msg}")
            console.print()
        
        # Show success with change summary
        console.print()
        console.print(f"[{get_heading_style()}]Configuration Updated[/{get_heading_style()}]")
        console.print()
        
        rows = [("Key", key)]
        if old_value is not None:
            rows.append(("Previous", _format_config_value(old_value)))
        rows.append(("New", _format_config_value(coerced)))
        
        card = create_detail_card(title="Change Summary", rows=rows)
        console.print(card)
        console.print()
        console.print(f"[{get_success_style()}]✓ Configuration saved to .indexed/config.toml[/{get_success_style()}]")
        console.print()
        
    except Exception as e:
        console.print()
        console.print(f"[{get_error_style()}]❌ Error: {e}[/{get_error_style()}]")
        console.print()
        raise typer.Exit(1)


@app.command("delete")
def delete_config(
    key: str = typer.Argument(..., help="Dot path to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a configuration key from workspace config."""
    config = ConfigService()
    
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
        console.print(f"[{get_warning_style()}]ℹ️  Key not found: {key}[/{get_warning_style()}]")
        console.print()
        return
    
    # Show confirmation prompt
    if not force:
        console.print()
        console.print(f"[{get_heading_style()}]Delete Configuration Key[/{get_heading_style()}]")
        console.print()
        
        rows = [
            ("Key", key),
            ("Value", _format_config_value(current_value)),
        ]
        
        card = create_detail_card(title="Current Value", rows=rows)
        console.print(card)
        console.print()
        console.print(f"[{get_warning_style()}]⚠️  This will remove the key from workspace config.[/{get_warning_style()}]")
        console.print()
        
        if not typer.confirm("Continue?", default=False):
            console.print("[dim]Cancelled[/dim]")
            console.print()
            return
    
    # Delete the key
    if config.delete(key):
        console.print()
        console.print(f"[{get_success_style()}]✓ Deleted {key}[/{get_success_style()}]")
        console.print()
    else:
        console.print()
        console.print(f"[{get_warning_style()}]ℹ️  Key not found: {key}[/{get_warning_style()}]")
        console.print()


@app.command("validate")
def validate():
    """Validate current configuration against registered specs."""
    config = ConfigService()
    errs = config.validate()
    
    console.print()
    console.print(f"[{get_heading_style()}]Configuration Validation[/{get_heading_style()}]")
    console.print()
    
    if not errs:
        # Success case - no errors
        success_card = Panel(
            Text("✓ All configuration values are valid", style=get_success_style()),
            border_style=get_success_style(),
            padding=get_card_padding(),
        )
        console.print(success_card)
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
            error_lines.append(Text("Suggestion: Use format https://company.atlassian.net", style=get_secondary_style()))
        
        content = Group(*error_lines)
        
        error_card = Panel(
            content,
            title=f"[{get_error_style()}]{title}[/{get_error_style()}]",
            border_style=get_error_style(),
            padding=get_card_padding(),
        )
        console.print(error_card)
        console.print()
    
    # Summary
    error_count = len(errs)
    plural = "error" if error_count == 1 else "errors"
    console.print(f"[{get_error_style()}]❌ {error_count} validation {plural} found[/{get_error_style()}]")
    console.print()
    
    raise typer.Exit(1)
