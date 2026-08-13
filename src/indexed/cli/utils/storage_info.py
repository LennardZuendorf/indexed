"""Storage mode information display utilities.

This module provides utilities to display which storage mode (global/local)
is being used for the current command.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Optional

from rich.console import Console

from .components.theme import (
    get_dim_style,
)
from .console import render_user_text

logger = logging.getLogger(__name__)


StorageMode = Literal["global", "local"]


def get_context_mode_override() -> Optional[StorageMode]:
    """Read ``mode_override`` off the active Typer/Click context.

    Typer >=0.26 vendors Click, so ``click.get_current_context()`` returns
    ``None`` inside a Typer command. Try the vendored context first.

    Returns:
        Optional[StorageMode]: The override set by the root callback, or
        ``None`` when there is no active context or no override.
    """
    for module, attr in (
        ("typer._click.globals", "get_current_context"),
        ("click", "get_current_context"),
    ):
        try:
            import importlib

            get_current_context = getattr(importlib.import_module(module), attr)
            ctx = get_current_context(silent=True)
        except Exception:
            logger.debug("Could not read context via %s", module, exc_info=True)
            continue
        if ctx is not None and ctx.obj:
            return ctx.obj.get("mode_override")
    return None


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
    # indicator embeds the storage path (content-derived) — never markup-parsed.
    console.print(render_user_text(indicator, style=get_dim_style()))

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


def display_storage_mode_for_command(console: Console) -> None:
    """
    Display the storage mode indicator for the current command.

    This should be called by commands after they initialize ConfigService.
    It determines the storage mode based on ConfigService state and displays
    a brief indicator to the user.

    Parameters:
        console (Console): Rich Console to print to.
    """
    from indexed.config import has_local_config, get_local_root, get_global_root

    from indexed.cli.composition import resolve_collections_context

    mode_override = get_context_mode_override()

    cli_ctx = resolve_collections_context(mode_override=mode_override)
    config_service = cli_ctx.config_service
    workspace = Path.cwd()
    local_exists = has_local_config(workspace)

    storage_path = (
        get_local_root(workspace) if cli_ctx.mode == "local" else get_global_root()
    )

    config_mode = None
    try:
        config_data = config_service.load_raw()
        config_mode = config_data.get("storage", {}).get("mode")
    except Exception:
        logger.debug("Failed to read config mode from store", exc_info=True)

    workspace_pref = config_service.get_workspace_preference()

    mode, reason = get_storage_mode_and_reason(
        has_local=local_exists,
        mode_override=mode_override,
        config_mode=config_mode if config_mode in ("local", "global") else None,
        workspace_pref=workspace_pref,
    )

    print_storage_info(
        console=console,
        mode=mode,
        path=storage_path,
        reason=reason,
        newline_before=False,
        newline_after=True,
    )
