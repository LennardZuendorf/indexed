"""Keep mutable spec metadata on Git's normal content merge path."""

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


def test_mutable_spec_ledgers_keep_normal_merge() -> None:
    attributes = _merge_attributes(*UNION_LEDGERS)
    assert attributes == {path: "unspecified" for path in UNION_LEDGERS}


def test_size_ceiling_keeps_normal_merge() -> None:
    attributes = _merge_attributes(NORMAL_MERGE)
    assert attributes[NORMAL_MERGE] != "union"


def test_divergent_frontmatter_reports_conflict(git_repo: Path) -> None:
    from tests.conftest import run_git

    spec = git_repo / ".spec"
    spec.mkdir()
    ledger = spec / "tech.md"
    ledger.write_text("---\nupdated: 2026-01-01\n---\n")
    (git_repo / ".gitattributes").write_text((REPO_ROOT / ".gitattributes").read_text())
    run_git(git_repo, "add", ".")
    run_git(git_repo, "commit", "-m", "base")
    base = run_git(git_repo, "branch", "--show-current").stdout.strip()
    run_git(git_repo, "checkout", "-b", "other")
    ledger.write_text("---\nupdated: 2026-02-01\n---\n")
    run_git(git_repo, "commit", "-am", "other")
    run_git(git_repo, "checkout", base)
    ledger.write_text("---\nupdated: 2026-03-01\n---\n")
    run_git(git_repo, "commit", "-am", "current")
    result = run_git(git_repo, "merge", "other", check=False)
    assert result.returncode != 0
    assert "<<<<<<<" in ledger.read_text()
