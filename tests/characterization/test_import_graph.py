"""Characterization: import-graph CI gate."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_import_graph.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_import_graph", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_import_graph_script_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (result.stderr or result.stdout).strip()


def test_check_import_graph_function_reports_no_violations() -> None:
    checker = _load_checker()
    violations = checker.check_import_graph(ROOT)
    assert violations == []


def test_core_importing_connectors_is_a_violation(tmp_path: Path) -> None:
    """core -> connectors is a forbidden cross-layer import and must be reported."""
    checker = _load_checker()
    core_dir = tmp_path / "packages/indexed-core/src/core"
    core_dir.mkdir(parents=True)
    (core_dir / "__init__.py").write_text("from connectors import something\n")
    connectors_dir = tmp_path / "packages/indexed-connectors/src/connectors"
    connectors_dir.mkdir(parents=True)
    (connectors_dir / "__init__.py").write_text("")

    violations = checker.check_import_graph(tmp_path)
    assert violations, "expected a violation for core -> connectors, got none"
    assert any("core must not import connectors" in v for v in violations)


def test_core_importing_indexed_is_a_violation(tmp_path: Path) -> None:
    """core -> indexed is a forbidden upward import that the old FORBIDDEN map missed silently."""
    checker = _load_checker()
    core_dir = tmp_path / "packages/indexed-core/src/core"
    core_dir.mkdir(parents=True)
    (core_dir / "__init__.py").write_text("from indexed import something\n")
    indexed_dir = tmp_path / "apps/indexed/src/indexed"
    indexed_dir.mkdir(parents=True)
    (indexed_dir / "__init__.py").write_text("")

    violations = checker.check_import_graph(tmp_path)
    assert violations, "expected a violation for core -> indexed, got none"
    assert any("core must not import indexed" in v for v in violations)
