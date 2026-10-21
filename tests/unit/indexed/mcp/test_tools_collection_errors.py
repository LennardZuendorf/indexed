"""MCP boundary: "unknown collection" vs "present but unusable" (#112).

``status()`` omits collections whose manifest can't be read, so an empty status is
ambiguous. Reporting a broken index as "not found" sends an agent hunting a typo.
"""

from __future__ import annotations

import json
from pathlib import Path

from indexed.mcp.tools import _unresolvable_collection_envelope


def _payload(base: Path, name: str, manifest: str | None) -> dict:
    if manifest is not None:
        (base / name).mkdir()
        (base / name / "manifest.json").write_text(manifest)
    return _unresolvable_collection_envelope(name, str(base))


def test_present_but_unusable_is_not_reported_as_missing(tmp_path: Path) -> None:
    corrupt = _payload(tmp_path, "broken", "{ not json")
    assert corrupt["type"] == "MCPError"
    assert "broken" in corrupt["error"]
    assert "not found" not in corrupt["error"]
    assert "has no usable index" in corrupt["error"]

    # Readable manifest, no indexers yet: also present, also not "not found".
    empty = _payload(tmp_path, "empty-indexers", json.dumps({"version": "1"}))
    assert "not found" not in empty["error"]


def test_unknown_collection_keeps_the_original_message(tmp_path: Path) -> None:
    assert _payload(tmp_path, "ghost", None) == {
        "error": "Collection 'ghost' not found or has no indexers"
    }
