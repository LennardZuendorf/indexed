"""Live proof: a real file edit reaches the collection with no manual update.

This drives the production watcher loop (``run_watch_loop`` + the real files
connector + the real v2 ingestion path) over a real temporary corpus, with the
embedding model mocked so the test is deterministic and network-free. Exactly
one file is written while the loop runs: if the collection content changes, the
watcher did it — nothing else called ``update``.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from typer.testing import CliRunner

from indexed.cli.app import app
from tests.unit.indexed.core.v2._engine_helpers import mock_embedding

runner = CliRunner()
COLLECTION = "watched-files"


def _create(path: Path):
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
            COLLECTION,
            "--path",
            str(path),
            "--local",
            "--no-cache",
        ],
    )


def _search(query: str) -> dict:
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
            COLLECTION,
            "--limit",
            "5",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _doc_ids(collections_dir: Path) -> set[str]:
    """Document ids currently in the collection's v2 docstore."""
    data = json.loads(
        (collections_dir / COLLECTION / "storage" / "docstore.json").read_text()
    )
    return {key.split("::")[0] for key in data["docstore/data"]}


def _watch_wiring(collections_path: Path):
    """The same scan/update closures the CLI command builds, for the loop."""
    from indexed.cli.composition import (
        resolve_collections_context,
        wiring_kwargs_for_update,
    )
    from indexed.core.engine import (
        SourceConfig,
        status as svc_status,
        update as run_update,
    )

    cli_ctx = resolve_collections_context(mode_override="local")
    statuses = svc_status([COLLECTION], collections_path=str(cli_ctx.collections_path))
    assert statuses, "collection must exist before watching"
    coll = statuses[0]
    source_config = SourceConfig(
        name=COLLECTION,
        type="localFiles",
        base_url_or_path="",
        indexer=coll.indexers[0],
    )
    wiring = wiring_kwargs_for_update(cli_ctx)

    def apply_update() -> None:
        cli_ctx.config_service.clear_overlay()
        run_update([source_config], **wiring)

    return apply_update


def test_live_edit_updates_the_collection_without_a_manual_update(
    local_workspace, files_corpus: Path
):
    from indexed.cli.knowledge.commands import watch_service

    with mock_embedding():
        created = _create(files_corpus)
        assert created.exit_code == 0, created.stdout + created.stderr

        collections_dir = local_workspace.collections_dir
        before = _doc_ids(collections_dir)
        assert before, "collection must be populated before the watcher starts"

        # Everything below is set up in the main thread; only the file write and
        # the stop signal happen on the helper thread.
        apply_update = _watch_wiring(collections_dir)
        stop = threading.Event()
        write_done = threading.Event()
        baseline_taken = threading.Event()

        def scan():
            # The first call IS the watcher's baseline snapshot. The edit must
            # land after it — otherwise the new file is part of the baseline and
            # no change is ever detected (a real race on a fast runner).
            signature = watch_service.signature_for(
                files_corpus, excluded_dirs=(), respect_gitignore=True
            )
            baseline_taken.set()
            return signature

        def edit_and_watch() -> None:
            assert baseline_taken.wait(timeout=10), "watcher never took a baseline"
            (files_corpus / "delta.txt").write_text(
                "The volcanic sulfur survey found deposits near the caldera rim.\n"
            )
            write_done.set()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if any(
                        doc.endswith("delta.txt") for doc in _doc_ids(collections_dir)
                    ):
                        break
                except (OSError, ValueError, KeyError):
                    pass  # the collection dir is briefly swapped mid-update
                time.sleep(0.05)
            stop.set()

        writer = threading.Thread(target=edit_and_watch, daemon=True)
        writer.start()

        code = watch_service.run_watch_loop(
            scan=scan,
            apply_update=apply_update,
            debounce_seconds=0.2,
            poll_interval_seconds=0.05,
            log_info=lambda message: None,
            log_error=lambda message: None,
            stop=stop,
        )
        writer.join(timeout=10)

        assert write_done.is_set()
        assert code == 0
        assert not writer.is_alive()

        after = _doc_ids(collections_dir)
        assert any(doc.endswith("delta.txt") for doc in after), (
            "the watcher must have indexed the new file without a manual update"
        )
        assert before.issubset(after), "pre-existing documents must survive the update"

        # Search runs inside the mock-embedding context: the point is that the new
        # document is in the searchable set, not that the ranking is meaningful.
        payload = _search("volcanic sulfur caldera deposits")

    assert any(r["document_id"].endswith("delta.txt") for r in payload["results"]), (
        "newly watched content must be searchable"
    )
