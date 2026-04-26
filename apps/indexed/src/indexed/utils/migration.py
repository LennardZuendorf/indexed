"""Migration utilities for indexed storage.

This module provides migration helpers for transitioning from the old
local ./data/ storage structure to the new global ~/.indexed/ structure.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

from .components.theme import (
    get_accent_style,
    get_dim_style,
    get_warning_style,
)
from .components import print_success, print_warning, print_error, create_detail_card


def _get_legacy_data_path() -> Path:
    """
    Return the legacy data directory path relative to the current working directory.

    Returns:
        Path: Path to the legacy data directory (current working directory joined with "data").
    """
    return Path.cwd() / "data"


def _get_legacy_collections_path() -> Path:
    """
    Return the path to the legacy collections directory located at ./data/collections.

    Returns:
        Path: The filesystem path pointing to the legacy `data/collections` directory.
    """
    return _get_legacy_data_path() / "collections"


def _get_legacy_caches_path() -> Path:
    """
    Resolve the legacy caches directory path under the current working directory.

    Returns:
        Path: Path to the legacy caches directory ('./data/caches').
    """
    return _get_legacy_data_path() / "caches"


def has_legacy_data() -> bool:
    """
    Determine whether any legacy collections exist under ./data/collections.

    Returns:
        True if at least one directory containing a `manifest.json` file exists in the legacy collections path, False otherwise.
    """
    legacy_path = _get_legacy_collections_path()
    if not legacy_path.exists() or not legacy_path.is_dir():
        return False

    # Check if there are any collections (directories with manifest.json)
    for item in legacy_path.iterdir():
        if item.is_dir() and (item / "manifest.json").exists():
            return True

    return False


def get_legacy_collections() -> list[str]:
    """
    Return the names of collections found in the legacy data directory.

    A collection is any subdirectory that contains a `manifest.json` file.

    Returns:
        A sorted list of collection names (subdirectory names) that contain a `manifest.json`.
    """
    legacy_path = _get_legacy_collections_path()
    if not legacy_path.exists() or not legacy_path.is_dir():
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
    """
    Migrate legacy "./data" contents into the specified target storage root under "data/".

    Copies legacy collection directories into {target_root}/data/collections and legacy cache items into {target_root}/data/caches, skipping items that already exist at the target and preserving the originals. When dry_run is True, reports what would be migrated without performing any file operations.

    Parameters:
        target_root (Path): Destination root for migrated data (e.g., ~/.indexed).
        console (Console): Rich Console used for user-facing output.
        dry_run (bool): If True, show actions without copying files.

    Returns:
        bool: `True` if migration completed successfully or no migration was needed, `False` if a failure occurred.
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
    names_display = ", ".join(collections[:10])
    if len(collections) > 10:
        names_display += f" +{len(collections) - 10} more"

    console.print()
    print_warning("Legacy data detected at ./data/")
    console.print(
        create_detail_card(
            title="Migration Available",
            rows=[
                ("Collections", str(len(collections))),
                ("Names", names_display),
                ("Source", "./data/"),
                ("Target", str(target_root / "data/")),
            ],
        )
    )
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
                print_warning(f"Skipping {collection} - already exists at target")
                continue

            console.print(f"[{get_dim_style()}]Copying {collection}...[/]")
            shutil.copytree(src, dst)

        # Copy caches if they exist
        if legacy_caches.exists():
            if legacy_caches.is_dir():
                # Legacy caches is a directory - iterate through items
                for cache_item in legacy_caches.iterdir():
                    src = cache_item
                    dst = target_caches / cache_item.name

                    if dst.exists():
                        continue

                    if cache_item.is_dir():
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
            else:
                # Legacy caches is a file - copy it directly
                dst = target_caches / legacy_caches.name
                if not dst.exists():
                    shutil.copy2(legacy_caches, dst)

        console.print()
        print_success("Migration complete!")
        console.print()
        console.print(
            f"[{get_dim_style()}]Note: Original data at ./data/ has been preserved.\n"
            f"You can delete it manually after verifying the migration.[/]"
        )
        console.print()

        return True

    except Exception as e:
        print_error(f"Migration failed: {e}")
        return False


def prompt_migration(
    console: Console,
    target_root: Path,
) -> bool:
    """
    Prompt the user to migrate legacy data from ./data into the provided target storage root.

    Parameters:
        console (Console): Rich Console used to display messages and prompts.
        target_root (Path): Destination root for migrated data (e.g., ~/.indexed).

    Returns:
        bool: `True` if migration succeeded or was not needed; `False` if user declined migration or a migration attempt failed.
    """
    if not has_legacy_data():
        return True

    # Check if target already has data
    target_collections = target_root / "data" / "collections"
    if (
        target_collections.exists()
        and target_collections.is_dir()
        and any(target_collections.iterdir())
    ):
        # Both have data - just inform user
        console.print()
        console.print(
            f"[{get_warning_style()}]Note:[/] Legacy data exists at ./data/ "
            f"but target {target_root}/data/ already has collections."
        )
        console.print(f"[{get_dim_style()}]Run 'indexed migrate' to merge them.[/]")
        console.print()
        return True

    # Prompt for migration
    collections = get_legacy_collections()

    console.print()
    console.print(f"[{get_warning_style()}]📦 Legacy data detected![/]")
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
        return False
