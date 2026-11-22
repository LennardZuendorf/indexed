"""Tests for ``scripts/check_spec_root.py`` — the spec root cannot drift back."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_spec_root.py"


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_spec_root", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate() -> ModuleType:
    return load_gate()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    spec = tmp_path / "docs" / "spec"
    spec.mkdir(parents=True)
    for name in ("product.md", "plan.md", "tech.md", "lessons.md"):
        (spec / name).write_text("# spec\n")
    return tmp_path


def _files(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    )


def test_sound_tree_passes(gate: ModuleType, tree: Path) -> None:
    assert gate.check(tree, _files(tree)) == []


def test_missing_spec_root_fails(gate: ModuleType, tmp_path: Path) -> None:
    assert gate.check(tmp_path, []) == ["docs/spec/ does not exist"]


def test_missing_core_spec_fails(gate: ModuleType, tree: Path) -> None:
    (tree / "docs" / "spec" / "plan.md").unlink()
    assert gate.check(tree, _files(tree)) == ["docs/spec/plan.md is missing"]


def test_legacy_directory_fails(gate: ModuleType, tree: Path) -> None:
    (tree / ".spec").mkdir()
    (tree / ".spec" / "tech.md").write_text("# old\n")
    problems = gate.check(tree, [*_files(tree)])
    assert any("legacy .spec/ still exists" in p for p in problems)
    assert any(p.startswith(".spec/tech.md: tracked") for p in problems)


@pytest.mark.parametrize(
    "line", ["read `.spec/tech.md`", 'root / ".spec"', "see .spec", "- .spec/"]
)
def test_reference_to_legacy_root_fails(
    gate: ModuleType, tree: Path, line: str
) -> None:
    (tree / "README.md").write_text(f"intro\n{line}\n")
    assert gate.check(tree, _files(tree)) == ["README.md:2: names .spec; use docs/spec"]


@pytest.mark.parametrize(
    "line",
    ["docs/spec/tech.md", "pkg.spec.ts", "importlib.util.spec_from_file_location"],
)
def test_unrelated_text_passes(gate: ModuleType, tree: Path, line: str) -> None:
    (tree / "README.md").write_text(f"{line}\n")
    assert gate.check(tree, _files(tree)) == []


def test_pinned_captures_are_exempt(gate: ModuleType, tree: Path) -> None:
    pinned = tree / "eval" / "corpus"
    pinned.mkdir(parents=True)
    (pinned / "agents-doc.md").write_text("read `.spec/` first\n")
    (tree / "eval" / "baseline.json").write_text('{"source": ".spec/tech.md"}\n')
    assert gate.check(tree, _files(tree)) == []


def test_binary_and_symlink_files_are_skipped(gate: ModuleType, tree: Path) -> None:
    (tree / "blob.bin").write_bytes(b"\xff\xfe.spec/")
    (tree / "CLAUDE.md").symlink_to(tree / "docs" / "spec" / "tech.md")
    assert gate.check(tree, _files(tree)) == []


def test_real_repository_is_sound(gate: ModuleType) -> None:
    assert gate.check(ROOT, gate.tracked_files(ROOT)) == []


def test_main_reports_success(
    gate: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.main() == 0
    assert "spec root OK" in capsys.readouterr().out


def test_main_reports_failure(
    gate: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "tracked_files", lambda root: [])
    assert gate.main() == 1
    assert "FAILED" in capsys.readouterr().err
