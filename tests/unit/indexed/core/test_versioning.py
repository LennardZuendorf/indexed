"""Unit tests for core-v2/1 engine detection (``indexed.core.versioning``).

Covers plan.md test scenarios 3 & 4: version markers map to engine versions,
an unknown marker fails loud without touching the collection, and a
missing/unreadable manifest reuses v1's existing collection-level error.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_manifest(collection_dir: Path, payload: dict) -> None:
    collection_dir.mkdir(parents=True, exist_ok=True)
    (collection_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_absent_version_key_is_v1(tmp_path: Path) -> None:
    from indexed.core.versioning import detect_engine_version

    coll = tmp_path / "legacy"
    _write_manifest(coll, {"collectionName": "legacy", "numberOfDocuments": 3})

    assert detect_engine_version(coll) == "1"


def test_explicit_version_one(tmp_path: Path) -> None:
    from indexed.core.versioning import detect_engine_version

    coll = tmp_path / "c1"
    _write_manifest(coll, {"version": "1", "collectionName": "c1"})

    assert detect_engine_version(coll) == "1"


def test_explicit_version_two(tmp_path: Path) -> None:
    from indexed.core.versioning import detect_engine_version

    coll = tmp_path / "c2"
    _write_manifest(coll, {"version": "2", "collectionName": "c2"})

    assert detect_engine_version(coll) == "2"


def test_unknown_version_raises_and_leaves_collection_untouched(tmp_path: Path) -> None:
    from indexed.core.errors import UnknownEngineVersionError
    from indexed.core.versioning import detect_engine_version

    coll = tmp_path / "future"
    payload = {"version": "3", "collectionName": "future"}
    _write_manifest(coll, payload)
    before = (coll / "manifest.json").read_bytes()
    dir_listing_before = sorted(p.name for p in coll.iterdir())

    with pytest.raises(UnknownEngineVersionError) as excinfo:
        detect_engine_version(coll)

    # Message names the found version and the supported set.
    message = str(excinfo.value)
    assert "3" in message
    assert "1" in message and "2" in message
    # Collection is not modified (R1: fail loud, touch nothing).
    assert (coll / "manifest.json").read_bytes() == before
    assert sorted(p.name for p in coll.iterdir()) == dir_listing_before


def test_unknown_version_error_is_indexed_error(tmp_path: Path) -> None:
    from indexed.config.errors import IndexedError
    from indexed.core.errors import UnknownEngineVersionError

    assert issubclass(UnknownEngineVersionError, IndexedError)


def test_missing_manifest_reuses_collection_level_error(tmp_path: Path) -> None:
    from indexed.core.versioning import detect_engine_version

    coll = tmp_path / "gone"
    coll.mkdir()

    # v1 raises a plain collection-level ValueError for a missing/unreadable
    # manifest (see inspect_service._read_manifest / update factory); detect
    # reuses that behavior rather than inventing a new error type.
    with pytest.raises(ValueError):
        detect_engine_version(coll)


def test_corrupt_manifest_reuses_collection_level_error(tmp_path: Path) -> None:
    from indexed.core.versioning import detect_engine_version

    coll = tmp_path / "corrupt"
    coll.mkdir()
    (coll / "manifest.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError):
        detect_engine_version(coll)
