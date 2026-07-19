"""System test: v1 -> v2 migration via the real CLI (core-v2/4, R7).

Builds a REAL v1 collection (default engine) over the shared files corpus, then
drives ``indexed index migrate`` end to end: a dry-run that changes nothing, an
OFFLINE migration (no ``--from-source``, no credentials) that produces a working
v2 collection preserving a ``<name>.v1-backup``, a post-migration SEARCH PARITY
spot-check (the same needle query that topped v1 tops the migrated v2), and a
standalone ``--purge-backup`` cleanup. A socket guard proves the offline default
makes zero outbound network connections. Gated on ``model_available()`` (real
embeddings).
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from tests.conftest import model_available

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

NEEDLE_QUERY = "penguin migration survey along the Antarctic coastline"


def _create_v1(collection: str, path: Path):
    return runner.invoke(
        app,
        [
            "--local",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--collection",
            collection,
            "--path",
            str(path),
            "--local",
            "--no-cache",
        ],
    )


def _migrate(collection: str, *flags: str):
    return runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "migrate",
            collection,
            *flags,
        ],
    )


def _search(query: str, collection: str, *, limit: int = 5) -> dict:
    result = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "search",
            query,
            "--collection",
            collection,
            "--limit",
            str(limit),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _search_all(query: str, *, limit: int = 5) -> dict:
    """Search ALL collections (no ``--collection``) — exercises the discovery
    path (``_existing_collection_names``) a single-collection search bypasses."""
    result = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "search",
            query,
            "--limit",
            str(limit),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _inspect_all() -> list:
    """List ALL collections via ``inspect`` (no name) — the all-collections
    discovery surface (``_existing_collection_names``)."""
    result = runner.invoke(
        app,
        ["--local", "--simple-output", "--log-level", "ERROR", "inspect"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _fingerprint(root: Path) -> dict:
    import hashlib

    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_v1_to_v2_migration_lifecycle(local_workspace, files_corpus: Path) -> None:
    ws = local_workspace
    collection = "files-migrate"

    # --- build a real v1 collection (default engine) ----------------------
    created = _create_v1(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr
    coll_dir = ws.collections_dir / collection
    v1_manifest = json.loads((coll_dir / "manifest.json").read_text())
    assert "version" not in v1_manifest  # unmarked == v1

    # v1 needle top-hit (the parity baseline).
    v1_hit = _search(NEEDLE_QUERY, collection)
    assert v1_hit["results"][0]["document_id"].endswith("needle.txt")

    # --- dry-run changes nothing (R7 scenario 1) --------------------------
    before = _fingerprint(coll_dir)
    dry = _migrate(collection, "--dry-run")
    assert dry.exit_code == 0, dry.stdout + dry.stderr
    dry_payload = json.loads(dry.stdout)
    assert dry_payload["status"] == "dry-run"
    assert dry_payload["dry_run"] is True
    assert dry_payload["documents"] == v1_manifest["numberOfDocuments"]
    assert "MiniLM" in dry_payload["embedding_model"]
    assert dry_payload["vector_store"] == "simple"
    assert _fingerprint(coll_dir) == before  # byte-identical
    assert not (ws.collections_dir / f"{collection}.v1-backup").exists()

    # --- offline migration (no --from-source, no creds) -------------------
    migrated = _migrate(collection)
    assert migrated.exit_code == 0, migrated.stdout + migrated.stderr
    mig_payload = json.loads(migrated.stdout)
    assert mig_payload["status"] == "migrate"
    assert mig_payload["validated"] is True

    v2_manifest = json.loads((coll_dir / "manifest.json").read_text())
    assert v2_manifest["version"] == "2"
    assert v2_manifest["engine"]["vectorStore"] == "simple"
    assert v2_manifest["numberOfDocuments"] == v1_manifest["numberOfDocuments"]

    # The v1 collection is preserved as the backup.
    backup = ws.collections_dir / f"{collection}.v1-backup"
    assert backup.is_dir()
    assert (backup / "manifest.json").is_file()
    assert "version" not in json.loads((backup / "manifest.json").read_text())

    # --- search parity: same needle query tops the migrated v2 (scenario 4)
    v2_hit = _search(NEEDLE_QUERY, collection)
    assert v2_hit["results"][0]["document_id"].endswith("needle.txt")
    assert "penguin" in v2_hit["results"][0]["text"].lower()

    # --- the retained <name>.v1-backup must NOT be discoverable/searchable ---
    # (pre-merge fix): while the backup is still on disk, the all-collections
    # surfaces (inspect/search WITHOUT --collection) must exclude it — else it
    # is listed AND searched, duplicating the migrated needle hit until purge.
    assert backup.is_dir()  # the backup is present for this check to be meaningful
    backup_name = f"{collection}.v1-backup"

    inspected = _inspect_all()
    listed = {c["name"] for c in inspected}
    assert collection in listed
    assert backup_name not in listed, f"backup surfaced in inspect: {sorted(listed)}"

    all_hits = _search_all(NEEDLE_QUERY)
    hit_collections = {r["collection"] for r in all_hits["results"]}
    assert backup_name not in hit_collections, (
        f"backup searched (duplicate hits): {sorted(hit_collections)}"
    )
    # The needle is returned from the migrated v2 collection ONLY — not also
    # from the backup (which would be a duplicate hit).
    needle_collections = {
        r["collection"]
        for r in all_hits["results"]
        if r["document_id"].endswith("needle.txt")
    }
    assert needle_collections == {collection}, needle_collections

    # --- standalone --purge-backup cleans up the backup -------------------
    purged = _migrate(collection, "--purge-backup")
    assert purged.exit_code == 0, purged.stdout + purged.stderr
    assert json.loads(purged.stdout)["status"] == "purge-backup"
    assert not backup.exists()
    # The migrated collection still works after the backup is gone.
    assert _search(NEEDLE_QUERY, collection)["results"][0]["document_id"].endswith(
        "needle.txt"
    )


def test_offline_migration_makes_no_network_connections(
    local_workspace, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R7 offline default at the system level: a default migrate (cached model)
    opens zero outbound connections — the credential-free stored-content path."""
    collection = "files-migrate-offline"
    created = _create_v1(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    class _NetworkAttempt(Exception):
        pass

    def _blocked_connect(self, address):  # noqa: ANN001
        raise _NetworkAttempt(f"network connect attempted: {address}")

    def _blocked_getaddrinfo(*args, **kwargs):  # noqa: ANN002, ANN003
        raise _NetworkAttempt(f"dns lookup attempted: {args}")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_getaddrinfo)

    migrated = _migrate(collection)
    assert migrated.exit_code == 0, migrated.stdout + migrated.stderr
    assert json.loads(migrated.stdout)["status"] == "migrate"

    payload = _search(NEEDLE_QUERY, collection)
    assert payload["results"][0]["document_id"].endswith("needle.txt")
