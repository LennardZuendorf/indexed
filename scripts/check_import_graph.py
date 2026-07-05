#!/usr/bin/env python3
"""Static import-graph checker for indexed monorepo layer rules.

Walks Python sources under packages/*/src and apps/*/src via AST and fails
when forbidden cross-package import edges are found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _make_package_roots(root: Path) -> tuple[tuple[Path, str], ...]:
    return (
        (root / "packages/indexed-core/src/core", "core"),
        (root / "packages/indexed-connectors/src/connectors", "connectors"),
        (root / "packages/indexed-config/src/indexed_config", "indexed_config"),
        (root / "packages/indexed-parsing/src/parsing", "parsing"),
        (root / "packages/indexed-protocols/src/protocols", "protocols"),
        (root / "packages/utils/src/utils", "utils"),
        (root / "apps/indexed/src/indexed", "indexed"),
    )


PACKAGE_ROOTS: tuple[tuple[Path, str], ...] = _make_package_roots(ROOT)

FORBIDDEN: dict[str, frozenset[str]] = {
    "core": frozenset({"connectors", "indexed"}),
    "connectors": frozenset({"core", "indexed"}),
    "indexed_config": frozenset({"core", "connectors", "indexed"}),
    "utils": frozenset({"core", "connectors", "indexed"}),
    "parsing": frozenset({"core", "connectors", "indexed"}),
    "protocols": frozenset({"core", "connectors", "indexed"}),
}


def _package_for_path(path: Path, root: Path | None = None) -> str | None:
    pkg_roots = _make_package_roots(root) if root is not None else PACKAGE_ROOTS
    resolved = path.resolve()
    for pkg_root, name in pkg_roots:
        try:
            resolved.relative_to(pkg_root.resolve())
        except ValueError:
            continue
        return name
    return None


def _iter_python_files(root: Path | None = None) -> list[Path]:
    base = root or ROOT
    files: list[Path] = []
    for pattern in ("packages/*/src", "apps/*/src"):
        for src_root in sorted(base.glob(pattern)):
            if src_root.is_dir():
                files.extend(sorted(src_root.rglob("*.py")))
    return files


def _top_level_module(module: str | None) -> str | None:
    if not module:
        return None
    return module.split(".", 1)[0]


def _imports_in_file(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:  # skip relative imports (from . import x)
                top = _top_level_module(node.module)
                if top:
                    imports.append((node.lineno, top))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = _top_level_module(alias.name)
                if top:
                    imports.append((node.lineno, top))
    return imports


def check_import_graph(root: Path | None = None) -> list[str]:
    """Return violation messages for forbidden import edges (empty if clean)."""
    violations: list[str] = []
    for path in _iter_python_files(root):
        source_pkg = _package_for_path(path, root)
        if source_pkg is None:
            continue
        forbidden = FORBIDDEN.get(source_pkg)
        if not forbidden:
            continue
        for lineno, imported in _imports_in_file(path):
            if imported in forbidden:
                rel = path.relative_to(root or ROOT)
                violations.append(
                    f"{rel}:{lineno}: {source_pkg} must not import {imported}"
                )
    return violations


def main() -> int:
    violations = check_import_graph()
    if violations:
        print("Forbidden import edges found:", file=sys.stderr)
        for message in violations:
            print(message, file=sys.stderr)
        return 1
    print("Import graph OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
