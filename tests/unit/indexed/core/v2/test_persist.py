"""Crash-safe directory swap tests (core-v2/2c ``persist.replace_dir``).

Mirrors the durability contract of v1's ``DiskPersister.replace_folder``: swap
in a built staging dir, overwrite an existing collection, and — critically —
leave the PRIOR collection intact when the swap fails mid-way (build-aside
crash-safety; PR #86 delete-before-persist regression).
"""

from __future__ import annotations

import os
import types
from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger

from indexed.core.v2.persist import replace_dir

pytestmark = pytest.mark.unit


@pytest.fixture
def logs() -> Iterator[list[str]]:
    """Capture loguru output so the operator-facing warnings can be asserted."""
    messages: list[str] = []
    handler = logger.add(lambda record: messages.append(str(record)), level="DEBUG")
    yield messages
    logger.remove(handler)


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


# ── failure injection: every step of the swap can fail (#126) ────────────────


def test_first_rename_failure_leaves_both_generations_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rename(dest -> trash)`` fails: nothing moved, nothing lost, error raises.

    The caller (``ingestion.create``) then discards only its own staging dir, so
    the original collection must still be exactly where it was.
    """
    dest = tmp_path / "dest"
    _mkdir_with(dest, "old")
    staging = tmp_path / "staging"
    _mkdir_with(staging, "new")

    def failing_rename(src, dst):  # noqa: ANN001
        raise OSError("rename1 boom")

    monkeypatch.setattr(os, "rename", failing_rename)

    with pytest.raises(OSError, match="rename1 boom"):
        replace_dir(staging, dest)

    assert (dest / "marker.txt").read_text() == "old"
    assert (staging / "marker.txt").read_text() == "new"
    assert not any(p.name.startswith("dest.trash-") for p in tmp_path.iterdir())


def test_rollback_failure_names_both_stranded_generations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logs: list[str]
) -> None:
    """Swap AND rollback fail: the canonical name is gone, but the data is not.

    Both generations stay on disk under names recovery understands, and the
    warning names both paths so an operator can act without guessing.
    """
    dest = tmp_path / "dest"
    _mkdir_with(dest, "old")
    staging = tmp_path / "staging"
    _mkdir_with(staging, "new")
    trash = tmp_path / f"dest.trash-{os.getpid()}"

    real_rename = os.rename
    state = {"calls": 0}

    def flaky_rename(src, dst):  # noqa: ANN001
        state["calls"] += 1
        if state["calls"] == 2:
            raise OSError("swap boom")
        if state["calls"] == 3:
            raise OSError("rollback boom")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", flaky_rename)

    with pytest.raises(OSError, match="swap boom"):
        replace_dir(staging, dest)

    assert state["calls"] == 3
    monkeypatch.setattr(os, "rename", real_rename)

    # Canonical path is missing, but neither generation was deleted: this is
    # exactly the state recovery restores from (see core.recovery tests).
    assert not dest.exists()
    assert (trash / "marker.txt").read_text() == "old"
    assert (staging / "marker.txt").read_text() == "new"

    warning = next(m for m in logs if "rollback failed" in m)
    assert str(trash) in warning
    assert str(staging) in warning


def test_residual_trash_cleanup_failure_keeps_the_new_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logs: list[str]
) -> None:
    """A cleanup that leaves entries must not damage the swapped-in collection."""
    dest = tmp_path / "dest"
    _mkdir_with(dest, "old")
    staging = tmp_path / "staging"
    _mkdir_with(staging, "new")
    trash = tmp_path / f"dest.trash-{os.getpid()}"

    from indexed.core.v2 import persist as persist_module

    # rmtree "succeeds" but leaves the directory behind (partial cleanup).
    monkeypatch.setattr(
        persist_module, "shutil", types.SimpleNamespace(rmtree=lambda *a, **k: None)
    )

    replace_dir(staging, dest)

    assert (dest / "marker.txt").read_text() == "new"
    assert (trash / "marker.txt").read_text() == "old"
    assert any("residual trash" in message for message in logs)
