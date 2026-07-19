"""Crash-safe directory swap tests (core-v2/2c ``persist.replace_dir``).

Mirrors the durability contract of v1's ``DiskPersister.replace_folder``: swap
in a built staging dir, overwrite an existing collection, and — critically —
leave the PRIOR collection intact when the swap fails mid-way (build-aside
crash-safety; PR #86 delete-before-persist regression).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from indexed.core.v2.persist import replace_dir

pytestmark = pytest.mark.unit


def _mkdir_with(path: Path, marker: str) -> None:
    path.mkdir(parents=True)
    (path / "marker.txt").write_text(marker, encoding="utf-8")


def test_replace_dir_into_empty_dest(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    _mkdir_with(staging, "new")
    dest = tmp_path / "dest"

    replace_dir(staging, dest)

    assert dest.is_dir()
    assert (dest / "marker.txt").read_text() == "new"
    assert not staging.exists()


def test_replace_dir_overwrites_existing_dest_and_leaves_no_trash(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "dest"
    _mkdir_with(dest, "old")
    staging = tmp_path / "staging"
    _mkdir_with(staging, "new")

    replace_dir(staging, dest)

    assert (dest / "marker.txt").read_text() == "new"
    assert not staging.exists()
    assert not any(p.name.startswith("dest.trash-") for p in tmp_path.iterdir())


def test_replace_dir_rolls_back_prior_collection_on_swap_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure on the staging->dest rename must restore the ORIGINAL dir under
    its name (never leave the collection missing) and re-raise."""
    dest = tmp_path / "dest"
    _mkdir_with(dest, "old")
    staging = tmp_path / "staging"
    _mkdir_with(staging, "new")

    real_rename = os.rename
    state = {"calls": 0}

    def flaky_rename(src, dst):  # noqa: ANN001
        state["calls"] += 1
        # call 1: dest -> trash (ok); call 2: staging -> dest (BOOM);
        # call 3: rollback trash -> dest (ok).
        if state["calls"] == 2:
            raise OSError("swap boom")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", flaky_rename)

    with pytest.raises(OSError, match="swap boom"):
        replace_dir(staging, dest)

    monkeypatch.setattr(os, "rename", real_rename)
    # The prior collection is restored intact under its expected name.
    assert dest.is_dir()
    assert (dest / "marker.txt").read_text() == "old"
