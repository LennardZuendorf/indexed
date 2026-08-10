"""Hidden debug command for build and environment diagnostics."""

from __future__ import annotations

import platform
import sys

import typer

from .utils.components import (
    create_key_value_panel,
    get_heading_style,
)
from .utils.console import console


def _pkg_version(name: str) -> str:
    """Return installed version of *name*, or 'not installed'."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


# External runtime dependencies surfaced in `indexed debug`. All internal code
# ships in the single `indexed-sh` distribution (shown as Version above), so
# there are no per-package internal versions to report.
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
    """Show release version, Python environment, and dependency versions."""
    app_version = _pkg_version("indexed-sh")

    rows_build: list[tuple[str, str]] = [
        ("Version", app_version),
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
        (label, _pkg_version(pkg)) for label, pkg in _EXTERNAL_DEPS
    ]

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
