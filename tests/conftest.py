"""Session-wide fixtures for isolated configuration.

This autouse fixture redirects global/workspace config paths used by
ConfigService so that tests cannot interact with real user or repository
configuration files. All tests run against temporary, empty TOML files
created inside a sandbox dir.

It also exposes the shared behavior-net scaffolding used by the
``tests/characterization`` suite (foundation/1): an isolated local workspace,
a real files corpus with a known "needle" document, and a collection builder
that drives the *real* engine (``DocumentCollectionCreator`` via
``create_collection_creator``) so tests exercise real FAISS + embeddings.
Stubbed-HTTP fixtures for the cloud connectors (jira/confluence/outline) live
alongside them and stub the network at the ``read_documents`` boundary only.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch

from indexed_config import ConfigService

# Canonical default indexer name (FAISS flat + all-MiniLM-L6-v2), matching the
# on-disk manifest the CLI produces.
DEFAULT_INDEXER_NAME = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


@pytest.fixture(scope="session", autouse=True)
def isolate_config_paths(tmp_path_factory: pytest.TempPathFactory):
    """Redirect config helper paths for the entire test session without using the
    function-scoped ``monkeypatch`` fixture (avoids ScopeMismatch errors).
    """

    mp = MonkeyPatch()

    sandbox_root = tmp_path_factory.mktemp("indexed_config_sandbox")

    # Create a fake HOME inside sandbox and point Path.home() to it
    sandbox_home = sandbox_root / "home"
    sandbox_home.mkdir(parents=True, exist_ok=True)

    # Create sandbox global root at ~/.indexed
    global_root = sandbox_home / ".indexed"
    global_root.mkdir(parents=True, exist_ok=True)
    (global_root / "config.toml").touch()

    # Also prepare a local root template (not overriding default behavior)
    local_template = sandbox_root / "local"
    local_template.mkdir(parents=True, exist_ok=True)
    (local_template / "config.toml").touch()

    # Patch Path.home to return sandbox_home so code using Path.home() is isolated
    mp.setattr(Path, "home", lambda: sandbox_home)

    # Reset ConfigService singleton for clean test state
    ConfigService.reset()

    yield  # run the test session

    # Teardown: undo monkeypatches and reset ConfigService singleton
    mp.undo()
    ConfigService.reset()


@pytest.fixture(autouse=True)
def reset_config_service():
    """Ensure ConfigService cache is cleared before and after each test."""
    ConfigService.reset()
    yield
    ConfigService.reset()


# ---------------------------------------------------------------------------
# Behavior-net scaffolding (foundation/1)
# ---------------------------------------------------------------------------


def model_available() -> bool:
    """True when the default embedding model is cached locally.

    The behavior net runs real embeddings; when the model is not cached the
    lifecycle tests skip rather than attempt a network download mid-suite.
    """
    try:
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        return is_model_cached("all-MiniLM-L6-v2")
    except Exception:
        return False


@pytest.fixture
def local_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An isolated ``./.indexed`` local workspace rooted at ``tmp_path``.

    Chdirs into ``tmp_path`` and materializes the local storage dirs, so every
    collection built or CLI command run under this fixture lands in the temp
    tree — never the real ``~/.indexed``. Returns a namespace with ``root``,
    ``local_root`` and ``collections_dir``.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TQDM_DISABLE", "1")
    from indexed_config import ensure_storage_dirs, get_local_root

    ConfigService.reset()
    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)
    collections_dir = local_root / "data" / "collections"
    return SimpleNamespace(
        root=tmp_path,
        local_root=local_root,
        collections_dir=collections_dir,
    )


@pytest.fixture
def files_corpus(tmp_path: Path) -> Path:
    """A small real files corpus with a known "needle" document.

    The needle carries a distinctive phrase used by the files lifecycle test to
    assert a *known* document is the top search hit — not merely "no error".
    """
    src = tmp_path / "corpus"
    src.mkdir()
    (src / "alpha.txt").write_text(
        "Semantic search finds documents by meaning rather than exact keywords.\n"
    )
    (src / "beta.txt").write_text(
        "Vector indexing and embeddings power modern document retrieval systems.\n"
    )
    (src / "needle.txt").write_text(
        "The penguin migration survey recorded record numbers along the "
        "Antarctic coastline this austral summer.\n"
    )
    return src


@pytest.fixture
def build_collection():
    """Return a helper that builds a real, searchable collection.

    Drives the same factory the CLI uses
    (``create_collection_creator`` → ``DocumentCollectionCreator.run``), so the
    on-disk layout (FAISS index, mappings, documents, manifest) is produced the
    way production produces it. Accepts any ``reader``/``converter`` pair, so
    both the files connector and stubbed cloud connectors flow through it with
    real FAISS + embeddings.
    """

    def _build(
        collections_dir: Path,
        name: str,
        reader,
        converter,
        *,
        indexer: str = DEFAULT_INDEXER_NAME,
        use_cache: bool = False,
    ) -> Path:
        from core.v1.engine.factories.create_collection_factory import (
            create_collection_creator,
        )

        creator = create_collection_creator(
            collection_name=name,
            indexers=[indexer],
            document_reader=reader,
            document_converter=converter,
            use_cache=use_cache,
            collections_path=str(collections_dir),
        )
        creator.run()
        return collections_dir / name

    return _build
