"""Tests for ``scripts/check_sizes.py`` — the LOC ceiling is derived, not stored.

Why this file exists: ``TEST_LOC_MAX`` is a single hand-bumped constant, so
every branch that adds tests edited the same line. Two such branches always
conflicted, and whichever number survived was wrong for the merged tree either
way (measured by hand: 55_810 vs 58_815 -> merged 58_839; 51_050 vs 52_600 ->
merged 52_431). The baseline mode measures *growth against a ref* instead, so
branches never touch a shared number. These tests pin its verdicts — base
moves, base missing, ref invalid, HEAD under/over the allowance, two branches
in combination — and prove the no-argument path still uses the absolute
ceilings exactly as before.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_sizes.py"

#: Git routing variables a hook or CI environment may export; left in place they
#: would point the temporary repositories below at the real object store.
_GIT_ROUTING_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)

_BUCKETS = {"src": "src/indexed/extra.py", "tests": "tests/test_extra.py"}


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_sizes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=size-gate",
            "-c",
            "user.email=size-gate@example.com",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repo),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def add_lines(repo: Path, relpath: str, count: int) -> None:
    """Append ``count`` lines to a tracked file, creating it if needed."""
    path = repo / relpath
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    body = "".join(f"# filler line {i}\n" for i in range(count))
    path.write_text(existing + body, encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal tree the structural checks accept, committed on ``main``."""
    for var in _GIT_ROUTING_VARS:
        monkeypatch.delenv(var, raising=False)
    repo = tmp_path / "repo"
    (repo / "src" / "indexed").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "indexed" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests" / "test_smoke.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    (repo / "AGENTS.md").write_text("# guide\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    git(repo, "init", "-b", "main")
    commit(repo, "base")
    return repo


def loc_of(repo: Path, relpath: str) -> int:
    return sum(1 for _ in (repo / relpath).open(encoding="utf-8"))


def test_growth_inside_the_allowance_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = load_gate()
    repo = make_repo(tmp_path, monkeypatch)
    base = git(repo, "rev-parse", "HEAD")
    add_lines(repo, _BUCKETS["tests"], gate.GROWTH_ALLOWANCE["tests"])
    commit(repo, "worst-case branch")

    violations, measurements = gate.check(repo, base)

    assert violations == [], violations
    assert any("allowance +" in line for line in measurements)


@pytest.mark.parametrize("bucket", ["tests", "src"])
def test_growth_one_line_past_the_allowance_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bucket: str
) -> None:
    gate = load_gate()
    repo = make_repo(tmp_path, monkeypatch)
    base = git(repo, "rev-parse", "HEAD")
    add_lines(repo, _BUCKETS[bucket], gate.GROWTH_ALLOWANCE[bucket] + 1)
    commit(repo, "one line too far")

    violations, _measurements = gate.check(repo, base)

    assert len(violations) == 1, violations
    assert "grew +" in violations[0]
    assert f"+{gate.GROWTH_ALLOWANCE[bucket]}" in violations[0]


def test_two_branches_that_each_add_tests_pass_in_combination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The conflict this replaces: both branches add tests, neither edits a ceiling.

    Under the stored-constant model each branch bumped the same line, so the
    pair conflicted and the surviving number fit neither tree. Here each branch
    is measured against the shared base, and the merged tree passes.
    """
    gate = load_gate()
    repo = make_repo(tmp_path, monkeypatch)
    base = git(repo, "rev-parse", "HEAD")

    git(repo, "checkout", "-b", "branch-a")
    add_lines(repo, "tests/test_a.py", 400)
    commit(repo, "a: tests")
    git(repo, "checkout", "-b", "branch-b", base)
    add_lines(repo, "tests/test_b.py", 600)
    commit(repo, "b: tests")
    git(repo, "checkout", "branch-a")
    git(repo, "merge", "--no-ff", "-m", "merge branch-b", "branch-b")

    # Neither branch needed to touch the shared constant: only test files differ
    # from the base, so there is nothing for a second branch to conflict on.
    changed = sorted(git(repo, "diff", "--name-only", base, "HEAD").splitlines())
    assert changed == ["tests/test_a.py", "tests/test_b.py"]

    violations, measurements = gate.check(repo, base)

    assert violations == [], violations
    assert any("(+1000 vs baseline" in line for line in measurements), measurements


def test_base_moving_forward_keeps_the_branch_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ceiling follows the base: main absorbing 250 lines must not fail the
    branch that only adds 50 more on top of it."""
    gate = load_gate()
    repo = make_repo(tmp_path, monkeypatch)
    add_lines(repo, "tests/test_main_growth.py", 250)
    commit(repo, "main moves")
    new_base = git(repo, "rev-parse", "HEAD")
    add_lines(repo, "tests/test_branch.py", 50)
    commit(repo, "branch adds 50")

    violations, measurements = gate.check(repo, new_base)

    assert violations == [], violations
    assert any("(+50 vs baseline" in line for line in measurements), measurements


def test_missing_baseline_commit_is_an_error_and_never_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = load_gate()
    repo = make_repo(tmp_path, monkeypatch)

    with pytest.raises(gate.SizeGateError, match="is not a tree"):
        gate.check(repo, "0" * 40)


def test_path_that_is_not_a_repository_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = load_gate()
    for var in _GIT_ROUTING_VARS:
        monkeypatch.delenv(var, raising=False)
    plain = tmp_path / "plain"
    (plain / "src" / "indexed").mkdir(parents=True)
    (plain / "tests").mkdir()
    (plain / "AGENTS.md").write_text("# guide\n", encoding="utf-8")
    (plain / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")

    with pytest.raises(gate.SizeGateError, match="not a git repository"):
        gate.check(plain, "HEAD")


def test_main_exits_two_on_an_unresolvable_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = load_gate()
    repo = make_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(gate, "ROOT", repo)

    assert gate.main(["--baseline-ref", "no-such-ref"]) == 2
    assert "Size gate error" in capsys.readouterr().err


def test_no_arguments_still_uses_the_absolute_ceilings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Requirement: ``python scripts/check_sizes.py`` behaves exactly as before."""
    gate = load_gate()
    repo = make_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(gate, "ROOT", repo)
    base = git(repo, "rev-parse", "HEAD")

    assert gate.main([]) == 0
    out = capsys.readouterr().out
    assert "LOC mode: absolute ceilings" in out
    assert f"(max {gate.TEST_LOC_MAX})" in out

    # The same growth is a violation once the (legacy) ceiling is tighter...
    monkeypatch.setattr(gate, "TEST_LOC_MAX", loc_of(repo, "tests/test_smoke.py") - 1)
    assert gate.main([]) == 1
    err = capsys.readouterr().err
    # ...and the message steers a branch to the baseline mode, not to bumping
    # this number (bumping it per branch is the conflict this change removes).
    assert "--baseline-ref origin/main" in err
    # ...while the baseline mode ignores the constant entirely.
    add_lines(repo, "tests/test_smoke.py", 5)
    commit(repo, "grow")
    assert gate.main(["--baseline-ref", base]) == 0
