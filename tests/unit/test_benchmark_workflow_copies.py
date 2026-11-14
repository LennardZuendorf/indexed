"""Pin the duplicated benchmark action inputs to a single value.

``.github/workflows/python-benchmark.yml`` measures twice — the PR job and the
dispatch-only baseline refresh — and GitHub Actions has no YAML merge keys, so
the action's ``with:`` block exists twice. PR #282 re-derived the caps from
main's baseline but changed only the PR job's copy, which left the refresh lane
reporting ``batch_parse`` against a 5 s cap its own baseline already exceeded.
Nothing in CI compares the two copies, so the divergence sat inside a green job.

This test is the comparison: the two maps must be byte-identical.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "python-benchmark.yml"
)


def _copies() -> list[str]:
    return re.findall(r"threshold-map: '([^']+)'", WORKFLOW.read_text(encoding="utf-8"))


def test_threshold_map_has_two_copies() -> None:
    """The PR job and the refresh job each carry the map."""
    assert len(_copies()) == 2


def test_threshold_map_copies_agree() -> None:
    """A cap changed in one job must be changed in the other."""
    pr_job, refresh_job = _copies()
    assert pr_job == refresh_job
