import ast
from pathlib import Path

CORE_ROOT = Path("packages/indexed-core/src/core")


def _python_files():
    return list(CORE_ROOT.rglob("*.py"))


def test_core_does_not_import_connectors_package():
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("connectors")
            ):
                violations.append(f"{path}:{node.lineno}: from {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("connectors"):
                        violations.append(f"{path}:{node.lineno}: import {alias.name}")
    assert not violations, "core must not import connectors:\n" + "\n".join(violations)
