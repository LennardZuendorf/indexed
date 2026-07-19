"""Characterization: import-graph CI gate (single-package layer checker)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_imports.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_imports", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_imports_script_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (result.stderr or result.stdout).strip()


def test_check_imports_function_reports_no_violations() -> None:
    checker = _load_checker()
    violations = checker.check(ROOT / "src" / "indexed")
    assert violations == []


def test_core_importing_connectors_is_a_violation(tmp_path: Path) -> None:
    """core -> connectors is a forbidden cross-layer import and must be reported."""
    checker = _load_checker()
    src = tmp_path / "src" / "indexed"
    core_dir = src / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "__init__.py").write_text("from indexed.connectors import something\n")
    (src / "connectors").mkdir(parents=True)
    (src / "connectors" / "__init__.py").write_text("")

    violations = checker.check(src)
    assert violations, "expected a violation for core -> connectors, got none"
    assert any("core must not import connectors" in v for v in violations)


def test_core_importing_cli_is_a_violation(tmp_path: Path) -> None:
    """core -> cli is a forbidden upward import (nothing may import the app layer)."""
    checker = _load_checker()
    src = tmp_path / "src" / "indexed"
    core_dir = src / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "__init__.py").write_text("from indexed.cli.app import something\n")
    (src / "cli").mkdir(parents=True)
    (src / "cli" / "__init__.py").write_text("")

    violations = checker.check(src)
    assert violations, "expected a violation for core -> cli, got none"
    assert any("core must not import cli" in v for v in violations)


def test_core_v2_importing_core_v1_is_a_violation(tmp_path: Path) -> None:
    """core/v2 -> core.v1 is forbidden: v2 is a self-contained engine (may use only
    protocols/config/utils + third-party), so it must never import the frozen v1
    engine internals. The generic 'core' bucket can't see the v1/v2 split."""
    checker = _load_checker()
    src = tmp_path / "src" / "indexed"
    v2_dir = src / "core" / "v2"
    v2_dir.mkdir(parents=True)
    (v2_dir / "ingestion.py").write_text(
        "from indexed.core.v1.engine import services\n"
    )

    violations = checker.check(src)
    assert violations, "expected a violation for core/v2 -> core.v1, got none"
    assert any("core/v2 must not import" in v for v in violations)


def test_core_v2_importing_protocols_and_core_errors_is_allowed(tmp_path: Path) -> None:
    """Legal v2 imports (protocols, core.errors) must NOT be flagged by the
    v2 -> v1 rule (guards against an over-broad match)."""
    checker = _load_checker()
    src = tmp_path / "src" / "indexed"
    v2_dir = src / "core" / "v2"
    v2_dir.mkdir(parents=True)
    (v2_dir / "stores.py").write_text(
        "from indexed.protocols import BaseConnector\n"
        "from indexed.core.errors import CoreV2Error\n"
    )

    violations = checker.check(src)
    assert violations == [], f"legal v2 imports were flagged: {violations}"
