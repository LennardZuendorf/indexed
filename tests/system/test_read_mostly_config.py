"""System test: runtime flows never write config.toml (R3, foundation/9).

An incremental update reconstructs the connector from its manifest and applies
the stored URL + a dated incremental query. Those must live in the in-memory
overlay only — ``config.toml`` (credential pointers included) must be
byte-identical before and after.
"""

import hashlib

from indexed_config import ConfigService, ensure_storage_dirs, get_local_root
from indexed import composition
from protocols import Manifest


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jira_manifest() -> Manifest:
    return Manifest.from_disk(
        {
            "collectionName": "jira-coll",
            "updatedTime": "2026-07-07T00:00:00+00:00",
            "lastModifiedDocumentTime": "2026-07-05T00:00:00+00:00",
            "numberOfDocuments": 2,
            "numberOfChunks": 20,
            "reader": {
                "type": "jira",
                "baseUrl": "https://jira.example.com",
                "query": "project = ENG",
            },
            "indexers": [{"name": "faiss-flat-l2"}],
        }
    )


def test_update_seam_leaves_config_toml_byte_stable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JIRA_TOKEN", "test-token")
    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)

    config_toml = local_root / "config.toml"
    config_toml.write_text(
        '[sources.jira]\nurl = "https://jira.example.com"\nquery = "project = ENG"\n',
        encoding="utf-8",
    )
    before = _sha(config_toml)

    ConfigService.reset()
    ctx = composition.resolve_collections_context(
        mode_override="local", workspace=tmp_path
    )
    factory = composition.make_manifest_factory(ctx)

    run = factory(
        _jira_manifest(),
        str(local_root / "data" / "collections" / "jira-coll"),
    )

    # The reader was rebuilt (the dated incremental query is applied) ...
    assert run.reader is not None
    # ... but the incremental query went to the in-memory overlay, NOT to disk.
    assert _sha(config_toml) == before, "update must not write config.toml (R3)"
