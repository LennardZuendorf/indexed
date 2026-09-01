"""System test: v2 engine CLI lifecycle — create/search/inspect/remove
(core-v2/2d, R4 surface parity).

Mirrors ``tests/characterization/test_lifecycle_files.py`` STYLE (real CLI via
``CliRunner``, real FAISS-free v2 collection, real embedding model, a KNOWN-HIT
search assertion) but for the v2 engine, and deliberately WITHOUT an update
step — v2 incremental update is core-v2/3's scope, which adds the FULL v2
lifecycle net (create->search->update->inspect->remove) alongside this one.
This file is scoped to create/search/inspect/remove so the two nets don't
duplicate coverage.
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

COLLECTION = "files-v2-net"


def _create_v2(collection: str, path: Path):
    return runner.invoke(
        app,
        [
            "--engine",
            "v2",
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


def test_v2_files_lifecycle_create_search_inspect_remove(
    local_workspace, files_corpus: Path
) -> None:
    ws = local_workspace

    # --- create (v2 engine, R1/R3) ----------------------------------------
    created = _create_v2(COLLECTION, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / COLLECTION / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["version"] == "2"
    assert manifest["engine"]["vectorStore"] == "simple"
    assert manifest["engine"]["scoreKind"] == "cosine"
    assert "MiniLM" in manifest["engine"]["embedding"]["model"]

    # --- search: a KNOWN document is the top hit (R4, R11 cosine) ---------
    payload = _search(
        "penguin migration survey along the Antarctic coastline", COLLECTION
    )
    assert payload["results"], "expected at least one search hit"
    top = payload["results"][0]
    assert top["document_id"].endswith("needle.txt")
    assert "penguin" in top["text"].lower()

    # A different query ranks a different document first (known-hit, not just
    # "no error").
    other = _search("vector indexing embeddings retrieval", COLLECTION)
    assert other["results"][0]["document_id"].endswith("beta.txt")

    # --- inspect: engine-aware diagnostics show v2 + model + store (R13) --
    inspected = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "inspect",
            COLLECTION,
        ],
    )
    assert inspected.exit_code == 0, inspected.stdout + inspected.stderr
    info = json.loads(inspected.stdout)
    assert info["engine"] == "2"
    assert info["vector_store"] == "simple"
    assert info["embedding_provider"] == "local"
    assert "MiniLM" in (info["embedding_model"] or "")

    # Rich (non-simple-output) inspect surfaces an engine indicator too.
    inspected_rich = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "inspect", COLLECTION]
    )
    assert inspected_rich.exit_code == 0, inspected_rich.stdout + inspected_rich.stderr
    assert COLLECTION in inspected_rich.stdout
    assert "v2" in inspected_rich.stdout

    # --- remove -------------------------------------------------------------
    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr
    assert not (ws.collections_dir / COLLECTION).exists()


def test_v2_default_create_and_search_never_touch_the_network(
    local_workspace, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8/R12 at the system level: a default v2 create+search (cached model)
    makes zero outbound network connections — the same socket-guard pattern
    core-v2/2b used for the embedding factory, applied here across the whole
    CLI create+search round trip."""
    collection = "files-v2-offline"

    class _NetworkAttempt(Exception):
        pass

    def _blocked_connect(self, address):  # noqa: ANN001
        raise _NetworkAttempt(f"network connect attempted: {address}")

    def _blocked_getaddrinfo(*args, **kwargs):  # noqa: ANN002, ANN003
        raise _NetworkAttempt(f"dns lookup attempted: {args}")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_getaddrinfo)

    created = _create_v2(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    payload = _search("penguin migration antarctic coastline", collection)
    assert payload["results"]
    assert payload["results"][0]["document_id"].endswith("needle.txt")

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", collection, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr


def test_v2_create_cli_replay_without_engine_flag_stays_v2(
    local_workspace, files_corpus: Path
) -> None:
    """CLI-level regression test for #185 — drives the real ``indexed index
    create`` command (through ``cli/knowledge/commands/_create_helpers.py``'s
    selector resolution), not the facade directly.

    ``core.engine.create()`` was fixed (see ``_resolve_existing_engine`` above
    ``create``) to defer to an existing collection's manifest when ``engine``
    is ``None`` — but ``_create_helpers.py`` always resolves a concrete engine
    string via ``resolve_engine_selector(engine_flag, config)`` (default
    ``"1"``) BEFORE calling the facade, and passes that resolved string
    unconditionally. So a bare CLI replay with no ``--engine`` never actually
    reaches the facade as ``engine=None`` — it reaches it as ``engine="1"``,
    which the fixed facade correctly (but unhelpfully) treats as an EXPLICIT
    conflicting request against an existing v2 collection and rejects with
    ``EngineMismatchError``, whose own message says "Re-run without --engine"
    — exactly what the user just did. The silent data loss from #185 is gone
    (confirmed: the collection's manifest ``version`` stays ``"2"``), but the
    fix's own intent (a no-flag replay should succeed and stay v2, matching
    ``update``/``clear`` and this module's own docstring) is not reachable
    from the real CLI. This test intentionally asserts that INTENDED
    behavior and is expected to fail until ``_create_helpers.py`` is changed
    to pass ``engine=None`` through when the user did not explicitly set
    ``--engine``/the env var/``[core] engine`` (mirroring how ``update.py``
    already does this).
    """
    ws = local_workspace
    collection = "flip-test-cli"

    created = _create_v2(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / collection / "manifest.json"
    assert json.loads(manifest_path.read_text())["version"] == "2"

    replayed = runner.invoke(
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
            str(files_corpus),
            "--force",
            "--no-cache",
        ],
    )

    assert replayed.exit_code == 0, (
        "a bare `indexed index create` replay (no --engine) against an "
        "existing v2 collection should succeed and stay v2, not error — "
        f"got exit={replayed.exit_code}: {replayed.stdout}{replayed.stderr}"
    )
    manifest_after = json.loads(manifest_path.read_text())
    assert manifest_after["version"] == "2"


def test_v2_create_cli_new_collection_env_var_still_selects_v2(
    local_workspace, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for the #185 fix's own blast radius: a GENUINELY NEW
    collection name with no ``--engine`` flag must still honor
    ``INDEXED__CORE__ENGINE`` via the full selector chain
    (``resolve_engine_selector``) in ``_create_helpers.py``.

    The #185 fix makes ``create`` pass the raw ``--engine`` flag (not the
    resolved selector) for an EXISTING collection name, so an unflagged
    replay defers to the manifest instead of the env/config default. That
    branch must not swallow the selector chain for a brand-new name too — if
    it did, a user with ``INDEXED__CORE__ENGINE=v2`` set and no ``--engine``
    flag creating a new collection would silently fall back to v1.
    """
    monkeypatch.setenv("INDEXED__CORE__ENGINE", "v2")
    collection = "new-collection-env-engine"

    created = runner.invoke(
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
            str(files_corpus),
            "--no-cache",
        ],
    )
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = local_workspace.collections_dir / collection / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["version"] == "2", (
        "a brand-new collection with INDEXED__CORE__ENGINE=v2 set and no "
        f"--engine flag must be created as v2, got version={manifest.get('version')!r}"
    )


def _replay_create(ws, collection: str, files_corpus: Path, *, engine):
    import indexed.core.engine as facade
    from indexed.connectors.files.connector import FileSystemConnector
    from indexed.core.v1.constants import DEFAULT_INDEXER

    facade.create(
        [
            facade.SourceConfig(
                name=collection,
                type="localFiles",
                base_url_or_path=str(files_corpus),
                indexer=DEFAULT_INDEXER,
            )
        ],
        engine=engine,
        use_cache=False,
        force=True,
        collections_path=str(ws.collections_dir),
        caches_path=str(ws.local_root / "data" / "caches"),
        connector_factory=lambda cfg: FileSystemConnector(path=str(files_corpus)),
    )


def test_v2_create_replay_without_engine_flag_stays_v2(
    local_workspace, files_corpus: Path
) -> None:
    """Regression test for #185 (E2E, real embeddings — complements the mocked
    unit test ``test_create_without_engine_on_existing_v2_collection_routes_to_v2``
    in ``test_engine_facade.py``).

    Before the #185 fix, ``indexed.core.engine.create`` was the one routed op
    that never checked a target collection's EXISTING on-disk manifest
    ``version`` before dispatching — a bare re-run with no ``--engine`` silently
    defaulted to v1, build-aside-and-swapped the whole collection directory, and
    destroyed the v2 index (manifest ``version`` went from ``"2"`` to absent/v1),
    no error raised. The fix routes a no-selector replay to the collection's
    OWN existing engine via ``_resolve_existing_engine`` (manifest-authoritative,
    matching ``update``/``clear``) — it must NOT raise, and must NOT flip to v1.
    """
    ws = local_workspace
    collection = "flip-test"

    created = _create_v2(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / collection / "manifest.json"
    manifest_before = json.loads(manifest_path.read_text())
    assert manifest_before["version"] == "2"

    # Re-run create on the SAME name, engine=None — must stay v2, not flip.
    _replay_create(ws, collection, files_corpus, engine=None)

    manifest_after = json.loads(manifest_path.read_text())
    assert manifest_after["version"] == "2", (
        "create() with no --engine flipped an existing v2 collection to a "
        f"different engine on replay (manifest version is now "
        f"{manifest_after.get('version')!r}) instead of routing to the "
        "collection's own existing engine."
    )


def test_v2_create_subcommand_engine_flag(local_workspace, files_corpus: Path) -> None:
    """core-v2-discoverability/1 (R1): `index create files --engine v2`
    (subcommand-level flag, not the root callback) succeeds and creates a v2
    collection — the primary Given/When/Then scenario in product.md."""
    ws = local_workspace
    collection = "files-v2-subcommand-flag"

    created = runner.invoke(
        app,
        [
            "--local",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--engine",
            "v2",
            "--collection",
            collection,
            "--path",
            str(files_corpus),
            "--local",
            "--no-cache",
        ],
    )
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / collection / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["version"] == "2"

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", collection, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr


def test_v2_create_subcommand_engine_replay_on_existing_collection(
    local_workspace, files_corpus: Path
) -> None:
    """core-v2-discoverability/1 (R1 test scenario 4): a subcommand-level
    `--engine v2` against an EXISTING v2 collection name still takes the
    raw-flag-only path (no full resolver chain) — same semantics as today's
    root-level `--engine` on the `collection_already_exists` branch. A
    matching engine is a no-op replay (succeeds, stays v2); this only proves
    the flag reaches the raw-flag path, not the env/config selector chain."""
    ws = local_workspace
    collection = "files-v2-subcommand-replay"

    created = _create_v2(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / collection / "manifest.json"
    assert json.loads(manifest_path.read_text())["version"] == "2"

    replayed = runner.invoke(
        app,
        [
            "--local",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--engine",
            "v2",
            "--collection",
            collection,
            "--path",
            str(files_corpus),
            "--force",
            "--no-cache",
        ],
    )
    assert replayed.exit_code == 0, replayed.stdout + replayed.stderr
    manifest_after = json.loads(manifest_path.read_text())
    assert manifest_after["version"] == "2"

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", collection, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr


def test_v2_root_engine_flag_only_still_works(
    local_workspace, files_corpus: Path
) -> None:
    """R1 test scenario 3 (regression, not new): `indexed --engine v2 index
    create files ...` — root-level flag only, no subcommand flag — behaves
    identically to before this unit (the subcommand flag is additive)."""
    ws = local_workspace
    collection = "files-v2-root-flag-only"

    created = _create_v2(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / collection / "manifest.json"
    assert json.loads(manifest_path.read_text())["version"] == "2"

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", collection, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr


def test_v2_create_replay_with_conflicting_engine_raises_mismatch(
    local_workspace, files_corpus: Path
) -> None:
    """Regression test for #185 (E2E, real embeddings — complements the mocked
    unit test ``test_create_engine_two_on_v1_marker_raises_mismatch`` in
    ``test_engine_facade.py``, exercised here in the opposite direction: an
    EXPLICIT conflicting ``--engine`` against a real, existing v2 collection).

    An explicit ``engine`` that conflicts with a collection's on-disk manifest
    must raise ``EngineMismatchError`` before any I/O — never silently replace
    the collection with the requested engine instead of the existing one.
    """
    from indexed.core.errors import EngineMismatchError

    ws = local_workspace
    collection = "flip-test-explicit"

    created = _create_v2(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / collection / "manifest.json"
    manifest_before = json.loads(manifest_path.read_text())
    assert manifest_before["version"] == "2"

    # Re-run create on the SAME name with an explicit conflicting engine="1".
    with pytest.raises(EngineMismatchError):
        _replay_create(ws, collection, files_corpus, engine="1")

    # The original v2 collection must be UNTOUCHED — no I/O before the raise.
    manifest_after = json.loads(manifest_path.read_text())
    assert manifest_after["version"] == "2", (
        "create() with an explicit conflicting --engine silently replaced the "
        f"v2 collection instead of raising EngineMismatchError before any I/O "
        f"(manifest version is now {manifest_after.get('version')!r})"
    )
