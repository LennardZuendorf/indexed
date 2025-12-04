"""Interactive conflict prompt for storage mode resolution.

This module provides a Rich-based interactive prompt for users to choose
between local and global storage when both configs exist with differences.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Literal, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

from .components.theme import (
    get_accent_style,
    get_card_border_style,
    get_dim_style,
    get_heading_style,
    get_label_style,
    get_success_style,
    get_warning_style,
)

# Type for the prompt result
ConflictChoice = Literal["global", "local", "global_remember", "local_remember"]


def format_value(value: Any, max_length: int = 40) -> str:
    """Format a config value for display, truncating if needed."""
    s = str(value)
    if len(s) > max_length:
        return s[: max_length - 3] + "..."
    return s


def show_config_differences(
    differences: Dict[str, tuple[Any, Any]],
    console: Console,
) -> None:
    """Display a table showing config differences between local and global.
    
    Args:
        differences: Dict mapping dot-paths to (local_value, global_value) tuples.
        console: Rich Console to print to.
    """
    if not differences:
        console.print("[dim]No differences found.[/dim]")
        return
    
    table = Table(
        title="Config Differences",
        box=box.ROUNDED,
        border_style=get_card_border_style(),
        show_header=True,
        header_style=get_heading_style(),
    )
    
    table.add_column("Setting", style=get_label_style())
    table.add_column("Local Value", style="yellow")
    table.add_column("Global Value", style="cyan")
    
    for path, (local_val, global_val) in differences.items():
        table.add_row(
            path,
            format_value(local_val),
            format_value(global_val),
        )
    
    console.print()
    console.print(table)
    console.print()


def prompt_storage_choice(
    console: Console,
    differences: Optional[Dict[str, tuple[Any, Any]]] = None,
    workspace_path: Optional[Path] = None,
) -> ConflictChoice:
    """Prompt user to choose between local and global storage.
    
    Args:
        console: Rich Console for output.
        differences: Optional dict of config differences to display.
        workspace_path: Optional workspace path to show in prompt.
        
    Returns:
        User's choice: "global", "local", "global_remember", or "local_remember"
    """
    workspace_display = str(workspace_path) if workspace_path else "current directory"
    
    # Show header
    console.print()
    console.print(
        Panel(
            f"[{get_warning_style()}]Both local and global configurations exist![/]",
            title="[bold]Storage Conflict Detected[/bold]",
            border_style=get_card_border_style(),
            padding=(1, 2),
        )
    )
    
    # Show differences if provided
    if differences:
        show_config_differences(differences, console)
    
    # Show options
    console.print(f"[{get_heading_style()}]Choose where to store data for:[/] {workspace_display}")
    console.print()
    console.print(f"  [{get_accent_style()}]1[/] - Use [bold]global[/bold] storage (~/.indexed)")
    console.print(f"  [{get_accent_style()}]2[/] - Use [bold]local[/bold] storage (./.indexed)")
    console.print(f"  [{get_accent_style()}]3[/] - Use [bold]global[/bold] and remember for this directory")
    console.print(f"  [{get_accent_style()}]4[/] - Use [bold]local[/bold] and remember for this directory")
    console.print()
    
    # Prompt for choice
    while True:
        choice = Prompt.ask(
            f"[{get_label_style()}]Enter choice[/]",
            choices=["1", "2", "3", "4"],
            default="1",
        )
        
        if choice == "1":
            return "global"
        elif choice == "2":
            return "local"
        elif choice == "3":
            return "global_remember"
        elif choice == "4":
            return "local_remember"


def show_storage_mode_info(
    console: Console,
    mode: Literal["global", "local"],
    remembered: bool = False,
) -> None:
    """Show a message about the selected storage mode.
    
    Args:
        console: Rich Console for output.
        mode: The storage mode being used.
        remembered: Whether this choice was remembered/persisted.
    """
    location = "~/.indexed" if mode == "global" else "./.indexed"
    
    if remembered:
        message = f"Using [{get_success_style()}]{mode}[/] storage ({location}) - preference saved"
    else:
        message = f"Using [{get_success_style()}]{mode}[/] storage ({location})"
    
    console.print()
    console.print(f"[{get_dim_style()}]→[/] {message}")
    console.print()


def handle_storage_conflict(
    console: Console,
    differences: Optional[Dict[str, tuple[Any, Any]]] = None,
    workspace_path: Optional[Path] = None,
) -> tuple[Literal["global", "local"], bool]:
    """Handle a storage conflict interactively.
    
    This is the main entry point for conflict resolution. It shows the
    conflict, prompts for a choice, and returns the result.
    
    Args:
        console: Rich Console for output.
        differences: Optional dict of config differences to display.
        workspace_path: Optional workspace path.
        
    Returns:
        Tuple of (chosen_mode, should_remember)
    """
    choice = prompt_storage_choice(
        console=console,
        differences=differences,
        workspace_path=workspace_path,
    )
    
    # Parse the choice
    if choice == "global":
        return ("global", False)
    elif choice == "local":
        return ("local", False)
    elif choice == "global_remember":
        return ("global", True)
    elif choice == "local_remember":
        return ("local", True)
    
    # Default fallback (shouldn't reach here)
    return ("global", False)




