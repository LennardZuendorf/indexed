"""Workspace-profile discovery — the upward search (workspace-profile/1, R2).

The workspace profile is a single committable TOML file. It is located by
walking *up* from the workspace directory, taking the first match of

1. ``<dir>/indexed.config.toml``   — canonical
2. ``<dir>/.indexed/config.toml``  — legacy (deprecated, still honoured)

in each directory. The walk is bounded by ``$HOME`` (inclusive) or the
filesystem root, whichever comes first.

**The legacy form is never matched at ``$HOME``** — ``~/.indexed/config.toml``
is the *global* config, not a workspace profile. Adopting it would silently
turn every home-rooted shell into a filtered workspace.
"""

from __future__ import annotations

from pathlib import Path

CANONICAL_NAME = "indexed.config.toml"
LEGACY_RELPATH = Path(".indexed") / "config.toml"


def find_profile(start: Path) -> tuple[Path, bool] | None:
    """Walk up from ``start`` looking for a workspace profile.

    Parameters:
        start: Directory to begin the search from (need not exist).

    Returns:
        ``(path, is_legacy)`` for the first hit, or ``None`` when no profile
        exists between ``start`` and the boundary. ``is_legacy`` is True only
        for the deprecated ``.indexed/config.toml`` form.
    """
    home = Path.home().expanduser().resolve()
    current = start.expanduser().resolve()

    while True:
        canonical = current / CANONICAL_NAME
        if canonical.is_file():
            return canonical, False

        # ~/.indexed/config.toml is the global config — never a profile.
        if current != home:
            legacy = current / LEGACY_RELPATH
            if legacy.is_file():
                return legacy, True

        if current == home or current == current.parent:
            return None
        current = current.parent
