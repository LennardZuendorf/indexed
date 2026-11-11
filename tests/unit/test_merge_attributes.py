"""Pin the union-merge attributes for the append-only spec ledgers.

Every branch appends its own dated entries to ``.spec/lessons.md`` (and, less
often, ``.spec/tech.md``), so an ordinary content merge conflicts on adjacent
tails even though both sides are wanted. ``.gitattributes`` declares
``merge=union`` for both files; without it every branch merge re-conflicts the
same hunks across the whole PR queue. ``scripts/check_sizes.py`` deliberately
keeps the default driver: its ceiling needs one decided number, and a union of
two ceilings would silently concatenate them.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UNION_LEDGERS = (".spec/lessons.md", ".spec/tech.md")
NORMAL_MERGE = "scripts/check_sizes.py"


def _merge_attributes(*paths: str) -> dict[str, str]:
    """Return ``git check-attr merge`` results keyed by repo-relative path."""
    git = shutil.which("git")
    if git is None:  # pragma: no cover - CI always has git
        pytest.skip("git is required to inspect merge attributes")
    assert git is not None
    completed = subprocess.run(
        [git, "check-attr", "merge", "--", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    attributes: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        path, _, rest = line.partition(": ")
        _, _, value = rest.partition(": ")
        attributes[path] = value
    return attributes


def test_append_only_ledgers_merge_by_union() -> None:
    attributes = _merge_attributes(*UNION_LEDGERS)
    assert attributes == {path: "union" for path in UNION_LEDGERS}


def test_size_ceiling_keeps_normal_merge() -> None:
    attributes = _merge_attributes(NORMAL_MERGE)
    assert attributes[NORMAL_MERGE] != "union"
