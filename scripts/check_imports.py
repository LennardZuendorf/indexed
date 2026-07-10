#!/usr/bin/env python3
"""Static layer-rule checker for the single ``indexed`` package.

Walks ``src/indexed`` via AST and fails on forbidden cross-subpackage import
edges. Subpackages are the first path component under ``src/indexed`` and the
first two components of an ``indexed.<sub>`` import.

Rules (top may import down; nothing imports up into cli/mcp):
  - core        ↛ connectors, cli, mcp
  - connectors  ↛ core, cli, mcp
  - config      ↛ core, connectors, cli, mcp   (may use only protocols/models)
  - parsing     ↛ core, connectors, cli, mcp
  - utils       ↛ core, connectors, cli, mcp
  - protocols   ↛ core, connectors, cli, mcp

Run with ``--self-test`` to verify a synthetic forbidden edge is caught.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "indexed"

_UP = frozenset({"cli", "mcp"})

# The `indexed config` CLI command lives at config/cli.py and its per-command
# modules under config/commands/ (merged there so they share the
# `indexed.config` command namespace, see simplify/3 & simplify/4). These are
# CLI-layer files — they may import core models and cli utils — so they are
# exempt from the config *package* purity rule. The config package modules
# themselves stay pure.
EXEMPT = frozenset({Path("config") / "cli.py"})
_EXEMPT_DIRS = frozenset({Path("config") / "commands"})


def _is_exempt(rel: Path) -> bool:
    """True for CLI-layer files that live inside the config package."""
    return rel in EXEMPT or any(parent in _EXEMPT_DIRS for parent in rel.parents)


FORBIDDEN: dict[str, frozenset[str]] = {
    "core": frozenset({"connectors"}) | _UP,
    "connectors": frozenset({"core"}) | _UP,
    "config": frozenset({"core", "connectors"}) | _UP,
    "parsing": frozenset({"core", "connectors"}) | _UP,
    "utils": frozenset({"core", "connectors"}) | _UP,
    "protocols": frozenset({"core", "connectors"}) | _UP,
}


def _imported_subpackages(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield (lineno, sub) for every absolute ``indexed.<sub>`` import."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        for mod in mods:
            parts = mod.split(".")
            if len(parts) >= 2 and parts[0] == "indexed":
                out.append((node.lineno, parts[1]))
    return out


def check(src: Path = SRC) -> list[str]:
    violations: list[str] = []
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src)
        if len(rel.parts) < 2:  # top-level module (e.g. __init__.py)
            continue
        if _is_exempt(rel):  # merged CLI command living inside a package dir
            continue
        source_sub = rel.parts[0]
        forbidden = FORBIDDEN.get(source_sub)
        if not forbidden:
            continue
        try:
            display = path.relative_to(ROOT)
        except ValueError:  # src outside the repo (e.g. a tmp tree in tests)
            display = path.relative_to(src)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, target in _imported_subpackages(tree):
            if target in forbidden:
                violations.append(
                    f"{display}:{lineno}: {source_sub} must not import {target}"
                )
    return violations


def _self_test() -> int:
    src = "from indexed.connectors.files import connector\nimport indexed.cli.app\n"
    tree = ast.parse(src)
    subs = {t for _, t in _imported_subpackages(tree)}
    forbidden = FORBIDDEN["core"]
    caught = subs & forbidden
    expected = {"connectors", "cli"}
    if caught != expected:
        print(
            f"SELF-TEST FAILED: caught {caught}, expected {expected}", file=sys.stderr
        )
        return 1
    print(f"self-test OK: forbidden edges detected for 'core' -> {sorted(caught)}")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    violations = check()
    if violations:
        print("Forbidden import edges found:", file=sys.stderr)
        for message in violations:
            print(message, file=sys.stderr)
        return 1
    print("Import graph OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
