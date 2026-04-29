"""Custom hatch build hook that stamps build metadata into the wheel.

Generates ``_build_meta.py`` with the UTC build timestamp and the current
git commit SHA so that the installed CLI can report exactly which build is
running — without bumping the version number.

The file is written to a temporary location and injected via
``force_include`` so it works reliably alongside the ``una-build`` hook.
"""

from __future__ import annotations

import datetime
import subprocess
import tempfile
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Stamp *_build_meta.py* into the package at wheel-build time."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        commit = _git_short_sha()

        # Write to a temp file and force-include it into the wheel.
        # This avoids relying on hatchling's file discovery (which runs
        # before hooks) and doesn't pollute the source tree.
        tmp = Path(tempfile.mkdtemp()) / "_build_meta.py"
        tmp.write_text(
            f'"""Auto-generated at build time by hatch_build.py — do not edit."""\n\n'
            f'BUILD_TIMESTAMP = "{timestamp}"\n'
            f'BUILD_COMMIT = "{commit}"\n',
            encoding="utf-8",
        )

        build_data["force_include"][str(tmp)] = "indexed/_build_meta.py"


def _git_short_sha() -> str:
    """Return the short SHA of HEAD, or ``"unknown"`` outside a git repo."""
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
