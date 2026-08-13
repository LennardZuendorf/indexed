"""Deterministic discovery-exclusion regression tests for ``core.v2._common``
(core-v2/2c review fix pass, Finding 2).

Complements ``test_ingestion.py::test_interrupted_create_staging_dir_excluded_from_discovery``
(which proves the FULL create-then-crash path end to end) with a static,
dependency-free check of BOTH discovery sites directly: ``_common.
discover_v2_collections`` and the facade's ``core.engine._existing_collection_names``.
Both use the same exclusion regex (``\\.(?:tmp|trash)-\\d+|\\.v1-backup$`` — a
digit immediately after ``-tmp``/``-trash``, OR a ``.v1-backup`` suffix), so
both must agree on every case, with fixed (non-random) dir names so the guard
cannot flaky-pass.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from indexed.core.engine import _existing_collection_names
from indexed.core.v2._common import discover_v2_collections


def _write_v2_manifest(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(
        json.dumps({"version": "2", "collectionName": directory.name}),
        encoding="utf-8",
    )


def test_digit_leading_and_pid_prefixed_staging_dirs_excluded_both_sites(
    tmp_path: Path,
) -> None:
    """A real collection stays discoverable; a legacy digit-leading stray
    (``mydocs.tmp-408afba6``) AND a fixed-naming stray whose uuid hex happens
    to start with a LETTER (``mydocs.tmp-<pid>-e288c54c`` — exactly the shape
    ``ingestion.create`` produces post-Finding-1) are BOTH excluded, at BOTH
    discovery sites: the digit run immediately after ``-tmp`` (either the
    whole legacy hex, or the pid in the fixed naming) is what the shared
    regex requires — a bare hex prefix is not sufficient, which is why the
    fix puts ``os.getpid()`` first.
    """
    base = tmp_path / "cols"
    _write_v2_manifest(base / "mydocs")
    _write_v2_manifest(base / "mydocs.tmp-408afba6")
    _write_v2_manifest(base / f"mydocs.tmp-{os.getpid()}-e288c54c")

    assert discover_v2_collections(base) == ["mydocs"]
    assert _existing_collection_names(str(base)) == ["mydocs"]


def test_v1_backup_dirs_excluded_both_sites(tmp_path: Path) -> None:
    """A migration's retained ``<name>.v1-backup`` (a complete v1 collection) is
    NOT surfaced by either discovery site — else ``inspect``/``status``/``search``
    (all-collections) list AND search the backup, duplicating the migrated hits
    until ``--purge-backup`` (core-v2 pre-merge fix). Both sites exclude any
    ``*.v1-backup`` dir BY NAME so they agree with the migration backup-name
    constant (``core/v2/migration.py`` -> ``f"{name}.v1-backup"``).
    """
    base = tmp_path / "cols"
    _write_v2_manifest(base / "mydocs")
    # The real backup is a v1 collection (unmarked manifest) — excluded from the
    # facade site by name (it still has a manifest.json, so it would otherwise
    # be listed).
    backup = base / "mydocs.v1-backup"
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "manifest.json").write_text(
        json.dumps({"collectionName": "mydocs"}), encoding="utf-8"
    )
    # A pathological v2-marked ``*.v1-backup`` proves the v2 site excludes by
    # NAME too (not merely because a v1 backup fails ``is_v2_collection``).
    _write_v2_manifest(base / "other.v1-backup")

    assert discover_v2_collections(base) == ["mydocs"]
    assert _existing_collection_names(str(base)) == ["mydocs"]
