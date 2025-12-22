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
    """
    Constructs a formatted indicator showing the storage mode, the storage root path (with the home directory replaced by `~`), and an optional reason.

    Parameters:
        mode (StorageMode): "global" or "local".
        path (Path): Path to the storage root.
        reason (Optional[str]): Optional explanation for using this mode.

    Returns:
        str: A single formatted string containing an icon, the capitalized mode label, the path, and the optional reason (e.g. "🌐 Global storage (~/.indexed) - via config setting").
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
    """
    Prints a formatted storage mode indicator to the given Rich Console.

    Parameters:
        console (Console): Rich Console to print to.
        mode (StorageMode): Storage mode label, either "global" or "local".
        path (Path): Path to the storage root; home directory may be shown as "~".
        reason (Optional[str]): Optional explanatory text appended to the indicator.
        newline_before (bool): If True, print a blank line before the indicator.
        newline_after (bool): If True, print a blank line after the indicator.
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
    """
    Resolve which storage mode to use and provide a short reason explaining the choice.

    Resolution precedence (highest to lowest): CLI override, config setting, workspace preference, presence of a local .indexed folder, then default to global.

    Parameters:
        has_local (bool): True if a local .indexed directory exists in the workspace.
        mode_override (Optional[StorageMode]): Mode explicitly specified via CLI flags.
        config_mode (Optional[StorageMode]): Mode from the project's config (e.g., config.toml).
        workspace_pref (Optional[StorageMode]): Previously saved workspace preference.

    Returns:
        tuple[StorageMode, str]: Chosen storage mode and a concise reason (e.g., "via --local flag", "via config setting", "saved preference", "local .indexed found", or "default").
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
