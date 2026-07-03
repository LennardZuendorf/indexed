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

PACKAGE_ROOTS: tuple[tuple[Path, str], ...] = (
    (ROOT / "packages/indexed-core/src/core", "core"),
    (ROOT / "packages/indexed-connectors/src/connectors", "connectors"),
    (ROOT / "packages/indexed-config/src/indexed_config", "indexed_config"),
    (ROOT / "packages/indexed-parsing/src/parsing", "parsing"),
    (ROOT / "packages/indexed-protocols/src/protocols", "protocols"),
    (ROOT / "packages/utils/src/utils", "utils"),
    (ROOT / "apps/indexed/src/indexed", "indexed"),
)

FORBIDDEN: dict[str, frozenset[str]] = {
    "core": frozenset({"connectors"}),
    "connectors": frozenset({"core"}),
    "indexed_config": frozenset({"core", "connectors", "indexed"}),
    "utils": frozenset({"core", "connectors", "indexed"}),
    "parsing": frozenset({"core", "connectors", "indexed"}),
    "protocols": frozenset({"core", "connectors", "indexed"}),
}


def _package_for_path(path: Path) -> str | None:
    resolved = path.resolve()
    for root, name in PACKAGE_ROOTS:
        try:
            resolved.relative_to(root.resolve())
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
        source_pkg = _package_for_path(path)
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
