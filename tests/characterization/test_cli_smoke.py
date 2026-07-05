"""Characterization: CLI search smoke test against a real on-disk collection.

The fixture collection is built through the real engine
(``DocumentCollectionCreator`` via ``create_collection_creator``) using the
FileSystem connector, rather than hand-encoding the on-disk format. This keeps
the test honest: if the persistence/index layout changes, the collection is
still produced the way the CLI produces it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.app import app

runner = CliRunner()

COLLECTION_NAME = "smoke-collection"
INDEXER_NAME = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


def _model_available() -> bool:
    try:
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        return is_model_cached("all-MiniLM-L6-v2")
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)


def _build_searchable_collection(
    collections_dir: Path, collection_name: str, source_dir: Path
) -> None:
    """Build a real, searchable collection from ``source_dir`` text files.

    Uses the same factory the CLI uses (``create_collection_creator``), which
    returns a ``DocumentCollectionCreator`` and persists a real FAISS index,
    document mapping, documents, and manifest via ``DiskPersister``.
    """
    from connectors.files.connector import FileSystemConnector
    from core.v1.engine.factories.create_collection_factory import (
        create_collection_creator,
    )

    connector = FileSystemConnector(
        path=str(source_dir),
        include_patterns=["*.txt"],
    )
    creator = create_collection_creator(
        collection_name=collection_name,
        indexers=[INDEXER_NAME],
        document_reader=connector.reader,
        document_converter=connector.converter,
        use_cache=False,
        collections_path=str(collections_dir),
    )
    creator.run()


@pytest.fixture
def smoke_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    from indexed_config import ensure_storage_dirs, get_local_root

    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)
    collections_dir = local_root / "data" / "collections"

    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    (source_dir / "alpha.txt").write_text(
        "Semantic search finds documents by meaning, not keywords."
    )
    (source_dir / "beta.txt").write_text(
        "This note also discusses semantic search and vector indexing."
    )

    _build_searchable_collection(collections_dir, COLLECTION_NAME, source_dir)
    return tmp_path


def test_cli_search_smoke(smoke_workspace: Path) -> None:
    del smoke_workspace
    result = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "search",
            "semantic search",
            "--collection",
            COLLECTION_NAME,
            "--limit",
            "3",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["query"] == "semantic search"
    assert payload["total_collections_searched"] >= 1
    assert isinstance(payload["results"], list)
    assert len(payload["results"]) >= 1
