"""Workspace-profile discovery — upward search (workspace-profile/1, R2).

Covers the upward walk from a workspace directory: canonical first, legacy
second, first hit wins, bounded by ``$HOME`` inclusive, and the trap that
``~/.indexed/config.toml`` is the GLOBAL config and must never be adopted as a
workspace profile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indexed.config.discovery import CANONICAL_NAME, LEGACY_RELPATH, find_profile


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A sandbox ``$HOME`` so the upward walk is bounded inside tmp_path."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: h))
    return h


def _mkdirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def test_finds_canonical_profile_in_parent_from_subdirectory(home: Path) -> None:
    """workspace-profile/1 R2: a shell deep in the tree finds the repo profile."""
    app = home / "code" / "app"
    sub = app / "src" / "api"
    _mkdirs(sub)
    profile = app / CANONICAL_NAME
    profile.write_text("[workspace]\n")

    assert find_profile(sub) == (profile, False)


def test_nearest_profile_wins_over_ancestor(home: Path) -> None:
    """workspace-profile/1 R2: the walk stops at the FIRST hit."""
    outer = home / "code"
    inner = outer / "app"
    _mkdirs(inner)
    (outer / CANONICAL_NAME).write_text("[workspace]\n")
    near = inner / CANONICAL_NAME
    near.write_text("[workspace]\n")

    assert find_profile(inner) == (near, False)


def test_legacy_location_resolves_and_is_flagged(home: Path) -> None:
    """workspace-profile/1 R2: ./.indexed/config.toml still works, flagged legacy."""
    app = home / "code" / "app"
    _mkdirs(app / ".indexed")
    legacy = app / LEGACY_RELPATH
    legacy.write_text("[workspace]\n")

    assert find_profile(app) == (legacy, True)


def test_canonical_wins_over_legacy_in_the_same_directory(home: Path) -> None:
    """workspace-profile/1 R2: canonical beats legacy when both are present."""
    app = home / "code" / "app"
    _mkdirs(app / ".indexed")
    canonical = app / CANONICAL_NAME
    canonical.write_text("[workspace]\n")
    (app / LEGACY_RELPATH).write_text("[workspace]\n")

    assert find_profile(app) == (canonical, False)


def test_walk_stops_at_home_inclusive(home: Path) -> None:
    """workspace-profile/1 R2: a canonical profile AT $HOME is still a profile."""
    sub = home / "scratch"
    _mkdirs(sub)
    profile = home / CANONICAL_NAME
    profile.write_text("[workspace]\n")

    assert find_profile(sub) == (profile, False)


def test_walk_does_not_escape_above_home(tmp_path: Path, monkeypatch) -> None:
    """workspace-profile/1 R2: a profile ABOVE $HOME is out of bounds."""
    h = tmp_path / "users" / "someone"
    sub = h / "code"
    _mkdirs(sub)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: h))
    (tmp_path / "users" / CANONICAL_NAME).write_text("[workspace]\n")

    assert find_profile(sub) is None


def test_global_config_is_never_adopted_as_a_profile(home: Path) -> None:
    """workspace-profile/1 R2: ~/.indexed/config.toml is the GLOBAL config.

    The legacy relpath happens to be exactly the global config's location, so
    the walk must refuse to match the legacy form at $HOME.
    """
    _mkdirs(home / ".indexed")
    (home / LEGACY_RELPATH).write_text("[core]\n")
    sub = home / "code" / "app"
    _mkdirs(sub)

    assert find_profile(sub) is None


def test_returns_none_when_no_profile_exists(home: Path) -> None:
    """workspace-profile/1 R2: no profile anywhere → unfiltered."""
    sub = home / "code" / "app"
    _mkdirs(sub)

    assert find_profile(sub) is None
