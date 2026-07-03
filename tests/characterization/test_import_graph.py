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
