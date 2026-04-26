"""Hidden debug command for build and environment diagnostics."""

from __future__ import annotations

import platform
import sys

import typer

from .utils.console import console
from .utils.components import (
    create_key_value_panel,
    get_heading_style,
)


def get_build_info() -> tuple[str, str]:
    """Return (build_timestamp, build_commit) with dev fallbacks."""
    try:
        from indexed._build_meta import BUILD_COMMIT, BUILD_TIMESTAMP

        return BUILD_TIMESTAMP, BUILD_COMMIT
    except ImportError:
        return "dev (editable install)", "n/a"


def _pkg_version(name: str) -> str:
    """Return installed version of *name*, or 'not installed'."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def _module_version(module_name: str, version_attr: str = "__version__") -> str:
    """Return version from a module's attribute, handling bundled packages.

    When una bundles workspace packages into the wheel, they lose their
    distribution metadata.  Fall back to importing the module and reading
    its version attribute directly.
    """
    dist_version = _pkg_version(module_name)
    if dist_version != "not installed":
        return dist_version

    # Try importing the module and reading its version attribute
    try:
        import importlib

        mod = importlib.import_module(module_name)
        return str(getattr(mod, version_attr, "bundled"))
    except ImportError:
        return "not installed"


# (label, package-name for importlib.metadata, module for fallback import, version attr)
_WORKSPACE_DEPS: list[tuple[str, str, str]] = [
    ("indexed-core", "core.v1", "__version__"),
    ("indexed-connectors", "connectors", "__version__"),
    ("indexed-parsing", "parsing", "__version__"),
    ("indexed-config", "indexed_config", "__version__"),
]

_EXTERNAL_DEPS: list[tuple[str, str]] = [
    ("sentence-transformers", "sentence-transformers"),
    ("faiss-cpu", "faiss-cpu"),
    ("docling", "docling"),
    ("torch", "torch"),
    ("typer", "typer"),
    ("fastmcp", "fastmcp"),
    ("pydantic", "pydantic"),
    ("rich", "rich"),
]


def debug(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show build metadata, Python environment, and dependency versions."""
    build_ts, build_commit = get_build_info()
    app_version = _pkg_version("indexed")

    rows_build: list[tuple[str, str]] = [
        ("Version", app_version),
        ("Build Timestamp", build_ts),
        ("Build Commit", build_commit),
    ]

    rows_env: list[tuple[str, str]] = [
        (
            "Python",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
        ("Platform", platform.platform()),
        ("Executable", sys.executable),
    ]

    rows_deps: list[tuple[str, str]] = [
        (label, _module_version(mod, attr)) for label, mod, attr in _WORKSPACE_DEPS
    ]
    rows_deps.extend((label, _pkg_version(pkg)) for label, pkg in _EXTERNAL_DEPS)

    if json_output:
        import json as json_mod

        data = {
            "build": dict(rows_build),
            "environment": dict(rows_env),
            "dependencies": dict(rows_deps),
        }
        console.print_json(json_mod.dumps(data))
        return

    console.print()
    console.print(f"[{get_heading_style()}]Indexed Debug Info[/{get_heading_style()}]")
    console.print()
    console.print(
        create_key_value_panel(
            "Build",
            rows_build,
            show_category=False,
            show_headers=False,
            key_width=22,
            value_max_len=80,
        )
    )
    console.print(
        create_key_value_panel(
            "Environment",
            rows_env,
            show_category=False,
            show_headers=False,
            key_width=22,
            value_max_len=80,
        )
    )
    console.print(
        create_key_value_panel(
            "Dependencies",
            rows_deps,
            show_category=False,
            show_headers=False,
            key_width=25,
            value_max_len=40,
        )
    )
    console.print()
