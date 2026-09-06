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
  - core/v2     ↛ core.v1   (v2 is self-contained: protocols/config/utils + 3rd-party only)
  - cli/mcp     ↛ core.v1, core.v2   (app layer uses only the core facade)

Run with ``--self-test`` to verify synthetic forbidden edges are caught.
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
# themselves stay pure. `cli/composition.py` is the app's composition root —
# its entire, sole purpose (per its own module docstring) is to wire every
# concrete v1/v2 config/connector type together by construction, so it is
# exempt from the cli/mcp -> core.v1/core.v2 facade-only rule below the same
# way config/cli.py is exempt from the config purity rule. Every OTHER
# cli/mcp file must go through the facade (core.engine/.errors/.versioning/
# .facade_config) — that's what the new deep rule now actually enforces.
EXEMPT = frozenset({Path("config") / "cli.py", Path("cli") / "composition.py"})
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


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield (lineno, module) for every absolute ``indexed.*`` import."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            out.extend((node.lineno, alias.name) for alias in node.names)
    return out


def _imported_subpackages(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield (lineno, sub) for every absolute ``indexed.<sub>`` import."""
    out: list[tuple[int, str]] = []
    for lineno, mod in _imported_modules(tree):
        parts = mod.split(".")
        if len(parts) >= 2 and parts[0] == "indexed":
            out.append((lineno, parts[1]))
    return out


def _v2_imports_v1(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield (lineno, module) for imports of ``indexed.core.v1`` — forbidden from
    ``core/v2`` (v2 is a self-contained engine that may use only
    protocols/config/utils + third-party, never the frozen v1 engine internals).
    The generic subpackage rule keys on the top-level ``core`` bucket and so
    cannot see the v1/v2 split; this deeper edge is checked explicitly."""
    hits: list[tuple[int, str]] = []
    for lineno, mod in _imported_modules(tree):
        if mod == "indexed.core.v1" or mod.startswith("indexed.core.v1."):
            hits.append((lineno, mod))
    return hits


def _app_layer_imports_core_v1_v2(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield (lineno, module) for a cli/mcp file importing indexed.core.v1.*
    or indexed.core.v2.* directly — forbidden (issue #186; .spec/tech.md "no
    code above the facade may import core.v1.*/core.v2.* directly"). The
    facade itself (core.engine, core.errors, core.versioning,
    core.facade_config) stays legal — only the v1/v2-internals dotted prefix
    is checked, mirroring _v2_imports_v1's shape for the same reason: the
    generic single-level FORBIDDEN dict can't see the v1/v2 split."""
    hits: list[tuple[int, str]] = []
    for lineno, mod in _imported_modules(tree):
        if mod.startswith("indexed.core.v1") or mod.startswith("indexed.core.v2"):
            hits.append((lineno, mod))
    return hits


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
        try:
            display = path.relative_to(ROOT)
        except ValueError:  # src outside the repo (e.g. a tmp tree in tests)
            display = path.relative_to(src)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        forbidden = FORBIDDEN.get(source_sub)
        if forbidden:
            for lineno, target in _imported_subpackages(tree):
                if target in forbidden:
                    violations.append(
                        f"{display}:{lineno}: {source_sub} must not import {target}"
                    )

        # Deeper edge: core/v2 must not import core.v1 (the generic 'core'
        # bucket rule above can't see the v1/v2 split).
        if source_sub == "core" and rel.parts[1] == "v2":
            for lineno, mod in _v2_imports_v1(tree):
                violations.append(
                    f"{display}:{lineno}: core/v2 must not import {mod} (v2 ↛ core.v1)"
                )

        # Deeper edge: cli/mcp must not import core.v1/core.v2 directly —
        # only the facade (core.engine/.errors/.versioning/.facade_config).
        if source_sub in _UP:
            for lineno, mod in _app_layer_imports_core_v1_v2(tree):
                violations.append(
                    f"{display}:{lineno}: {source_sub} must not import {mod} directly (use the core facade)"
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
    # v2 ↛ core.v1: a synthetic core/v2 file importing core.v1 IS caught...
    v2_bad = ast.parse(
        "from indexed.core.v1.engine import services\nimport indexed.core.v1.constants\n"
    )
    if len(_v2_imports_v1(v2_bad)) != 2:
        print(
            f"SELF-TEST FAILED: v2->v1 caught {_v2_imports_v1(v2_bad)}, expected 2",
            file=sys.stderr,
        )
        return 1
    # ...while a legal v2 import (protocols, core.errors) is NOT flagged.
    v2_ok = ast.parse(
        "from indexed.protocols import BaseConnector\n"
        "from indexed.core.errors import CoreV2Error\n"
    )
    if _v2_imports_v1(v2_ok):
        print(
            f"SELF-TEST FAILED: legal v2 import flagged: {_v2_imports_v1(v2_ok)}",
            file=sys.stderr,
        )
        return 1
    # cli/mcp ↛ core.v1/core.v2: a synthetic mcp file importing core.v1 IS caught...
    app_bad = ast.parse("from indexed.core.v1.config_models import MCPConfig\n")
    if len(_app_layer_imports_core_v1_v2(app_bad)) != 1:
        print(
            f"SELF-TEST FAILED: mcp->core.v1 caught "
            f"{_app_layer_imports_core_v1_v2(app_bad)}, expected 1",
            file=sys.stderr,
        )
        return 1
    # ...while importing the facade itself is NOT flagged.
    app_ok = ast.parse(
        "from indexed.core.engine import search\n"
        "from indexed.core.facade_config import MCPConfig\n"
    )
    if _app_layer_imports_core_v1_v2(app_ok):
        print(
            f"SELF-TEST FAILED: legal facade import flagged: "
            f"{_app_layer_imports_core_v1_v2(app_ok)}",
            file=sys.stderr,
        )
        return 1
    print(
        f"self-test OK: forbidden edges detected for 'core' -> {sorted(caught)}; "
        "v2 ↛ core.v1 enforced"
    )
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
