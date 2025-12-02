"""Storage mode information display utilities.

This module provides utilities to display which storage mode (global/local)
is being used for the current command.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from rich.console import Console

from .components.theme import (
    get_dim_style,
)


StorageMode = Literal["global", "local"]


def get_storage_indicator(
    mode: StorageMode,
    path: Path,
    reason: Optional[str] = None,
) -> str:
    """Get a formatted storage mode indicator string.
    
    Args:
        mode: The storage mode ("global" or "local").
        path: The storage root path.
        reason: Optional reason for using this mode.
        
    Returns:
        Formatted indicator string.
    """
    icon = "🌐" if mode == "global" else "📁"
    mode_display = mode.capitalize()
    path_display = str(path).replace(str(Path.home()), "~")
    
    if reason:
        return f"{icon} {mode_display} storage ({path_display}) - {reason}"
    return f"{icon} {mode_display} storage ({path_display})"


def print_storage_info(
    console: Console,
    mode: StorageMode,
    path: Path,
    reason: Optional[str] = None,
    *,
    newline_before: bool = False,
    newline_after: bool = True,
) -> None:
    """Print a storage mode indicator to the console.
    
    Args:
        console: Rich Console to print to.
        mode: The storage mode ("global" or "local").
        path: The storage root path.
        reason: Optional reason for using this mode.
        newline_before: Add newline before the message.
        newline_after: Add newline after the message.
    """
    if newline_before:
        console.print()
    
    indicator = get_storage_indicator(mode, path, reason)
    console.print(f"[{get_dim_style()}]{indicator}[/]")
    
    if newline_after:
        console.print()


def get_storage_mode_and_reason(
    has_local: bool,
    mode_override: Optional[StorageMode],
    config_mode: Optional[StorageMode],
    workspace_pref: Optional[StorageMode],
) -> tuple[StorageMode, str]:
    """Determine storage mode and the reason for using it.
    
    Resolution order:
    1. CLI flag (--local or --global)
    2. Config setting (storage.mode in config.toml)
    3. Workspace preference (saved from previous --local use)
    4. Local exists -> use local
    5. Default to global
    
    Args:
        has_local: Whether local .indexed folder exists.
        mode_override: Explicit mode from CLI flag.
        config_mode: Mode from config.toml storage.mode setting.
        workspace_pref: Workspace preference from global config.
        
    Returns:
        Tuple of (mode, reason_string).
    """
    if mode_override == "local":
        return ("local", "via --local flag")
    if mode_override == "global":
        return ("global", "via --global flag")
    
    if config_mode == "local":
        return ("local", "via config setting")
    if config_mode == "global":
        return ("global", "via config setting")
    
    if workspace_pref == "local":
        return ("local", "saved preference")
    if workspace_pref == "global":
        return ("global", "saved preference")
    
    if has_local:
        return ("local", "local .indexed found")
    
    return ("global", "default")


