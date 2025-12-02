"""Migration utilities for indexed storage.

This module provides migration helpers for transitioning from the old
local ./data/ storage structure to the new global ~/.indexed/ structure.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from .components.theme import (
    get_accent_style,
    get_card_border_style,
    get_dim_style,
    get_success_style,
    get_warning_style,
)


def _get_legacy_data_path() -> Path:
    """Get the legacy data path (./data)."""
    return Path.cwd() / "data"


def _get_legacy_collections_path() -> Path:
    """Get the legacy collections path (./data/collections)."""
    return _get_legacy_data_path() / "collections"


def _get_legacy_caches_path() -> Path:
    """Get the legacy caches path (./data/caches)."""
    return _get_legacy_data_path() / "caches"


def has_legacy_data() -> bool:
    """Check if legacy data exists at ./data/collections.
    
    Returns:
        True if legacy collections directory exists and has content.
    """
    legacy_path = _get_legacy_collections_path()
    if not legacy_path.exists():
        return False
    
    # Check if there are any collections (directories with manifest.json)
    for item in legacy_path.iterdir():
        if item.is_dir() and (item / "manifest.json").exists():
            return True
    
    return False


def get_legacy_collections() -> list[str]:
    """Get list of collection names in legacy data directory.
    
    Returns:
        List of collection names found in ./data/collections.
    """
    legacy_path = _get_legacy_collections_path()
    if not legacy_path.exists():
        return []
    
    collections = []
    for item in legacy_path.iterdir():
        if item.is_dir() and (item / "manifest.json").exists():
            collections.append(item.name)
    
    return sorted(collections)


def migrate_legacy_data(
    target_root: Path,
    console: Console,
    dry_run: bool = False,
) -> bool:
    """Migrate legacy data from ./data to target storage root.
    
    Args:
        target_root: Target storage root (e.g., ~/.indexed)
        console: Rich Console for output.
        dry_run: If True, only show what would be migrated without copying.
        
    Returns:
        True if migration was successful, False otherwise.
    """
    legacy_collections = _get_legacy_collections_path()
    legacy_caches = _get_legacy_caches_path()
    
    target_collections = target_root / "data" / "collections"
    target_caches = target_root / "data" / "caches"
    
    collections = get_legacy_collections()
    
    if not collections:
        console.print(f"[{get_dim_style()}]No legacy data found to migrate.[/]")
        return True
    
    # Show what will be migrated
    console.print()
    console.print(
        Panel(
            f"[{get_warning_style()}]Legacy data detected at ./data/[/]\n\n"
            f"Found [{get_accent_style()}]{len(collections)}[/] collection(s):\n"
            + "\n".join(f"  • {name}" for name in collections[:10])
            + (f"\n  ... and {len(collections) - 10} more" if len(collections) > 10 else ""),
            title="[bold]Migration Available[/bold]",
            border_style=get_card_border_style(),
            padding=(1, 2),
        )
    )
    console.print()
    console.print(f"[{get_dim_style()}]Source: ./data/[/]")
    console.print(f"[{get_dim_style()}]Target: {target_root}/data/[/]")
    console.print()
    
    if dry_run:
        console.print(f"[{get_dim_style()}]Dry run - no changes made.[/]")
        return True
    
    try:
        # Create target directories
        target_collections.mkdir(parents=True, exist_ok=True)
        target_caches.mkdir(parents=True, exist_ok=True)
        
        # Copy collections
        for collection in collections:
            src = legacy_collections / collection
            dst = target_collections / collection
            
            if dst.exists():
                console.print(
                    f"[{get_warning_style()}]⚠️  Skipping {collection} - already exists at target[/]"
                )
                continue
            
            console.print(f"[{get_dim_style()}]Copying {collection}...[/]")
            shutil.copytree(src, dst)
        
        # Copy caches if they exist
        if legacy_caches.exists():
            for cache_item in legacy_caches.iterdir():
                src = cache_item
                dst = target_caches / cache_item.name
                
                if dst.exists():
                    continue
                
                if cache_item.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        
        console.print()
        console.print(f"[{get_success_style()}]✓ Migration complete![/]")
        console.print()
        console.print(
            f"[{get_dim_style()}]Note: Original data at ./data/ has been preserved.\n"
            f"You can delete it manually after verifying the migration.[/]"
        )
        console.print()
        
        return True
        
    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        return False


def prompt_migration(
    console: Console,
    target_root: Path,
) -> bool:
    """Prompt user to migrate legacy data if it exists.
    
    Args:
        console: Rich Console for output.
        target_root: Target storage root (e.g., ~/.indexed).
        
    Returns:
        True if migration was performed (or not needed), False if user declined.
    """
    if not has_legacy_data():
        return True
    
    # Check if target already has data
    target_collections = target_root / "data" / "collections"
    if target_collections.exists() and any(target_collections.iterdir()):
        # Both have data - just inform user
        console.print()
        console.print(
            f"[{get_warning_style()}]Note:[/] Legacy data exists at ./data/ "
            f"but target {target_root}/data/ already has collections."
        )
        console.print(
            f"[{get_dim_style()}]Run 'indexed migrate' to merge them.[/]"
        )
        console.print()
        return True
    
    # Prompt for migration
    collections = get_legacy_collections()
    
    console.print()
    console.print(
        f"[{get_warning_style()}]📦 Legacy data detected![/]"
    )
    console.print(
        f"Found {len(collections)} collection(s) at ./data/ that can be "
        f"migrated to {target_root}/data/"
    )
    console.print()
    
    should_migrate = Confirm.ask(
        f"[{get_accent_style()}]Migrate now?[/]",
        default=True,
    )
    
    if should_migrate:
        return migrate_legacy_data(target_root, console)
    else:
        console.print()
        console.print(
            f"[{get_dim_style()}]Skipped. Run 'indexed migrate' later to migrate.[/]"
        )
        console.print()
        return True


