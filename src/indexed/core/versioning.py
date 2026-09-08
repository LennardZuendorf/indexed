"""Per-collection engine detection for the version-dispatching facade (core-v2/1).

Reads only ``<collection_path>/manifest.json`` (small) and maps the on-disk
``version`` marker to an engine version. Pre-v2 collections have no ``version``
key and detect as ``"1"``. Detection fails before any other I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from indexed.core.errors import UnknownEngineVersionError

EngineVersion = Literal["1", "2"]


def detect_engine_version(collection_path: Path) -> EngineVersion:
    """Return the engine version for a collection from its manifest marker.

    Rules (tech.md §Engine detection):

    - ``manifest.json`` absent/unreadable → the same collection-level
      ``ValueError`` v1 already raises for a missing/corrupt manifest (see
      ``inspect_service._read_manifest`` / the v1 update factory). Reused, not
      reinvented, so inspect/remove of a corrupt collection stay unchanged.
    - ``version`` key absent → ``"1"`` (all pre-v2 collections).
    - ``version == "1"`` → ``"1"``; ``version == "2"`` → ``"2"``.
    - any other value → :class:`UnknownEngineVersionError` (fail loud; the
      collection is not modified).
    """
    manifest_path = collection_path / "manifest.json"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # FileNotFoundError (missing) and json.JSONDecodeError (corrupt) both
        # land here — match v1's collection-level ValueError phrasing.
        raise ValueError(
            f"Could not read manifest for collection {collection_path.name}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"Could not read manifest for collection {collection_path.name}: "
            f"manifest is not a JSON object"
        )

    version = raw.get("version")
    if version is None:
        return "1"
    if version == "1":
        return "1"
    if version == "2":
        return "2"
    raise UnknownEngineVersionError(found=version, path=str(manifest_path))


__all__ = ["EngineVersion", "detect_engine_version"]
