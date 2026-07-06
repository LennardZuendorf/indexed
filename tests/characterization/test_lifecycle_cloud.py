"""Characterization: full cloud-source lifecycle behavior net (foundation/1).

For each cloud connector (jira / confluence / outline) drives the whole
lifecycle with the network stubbed at the ``read_documents`` boundary and real
FAISS + embeddings on small fixtures:

    create -> search (known doc is the top hit) -> incremental update
    (new doc becomes searchable) -> inspect (doc count) -> remove (gone).

Green characterization tests: they pin current CORRECT behavior and must stay
green through every foundation refactor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import model_available

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

SOURCES = ["jira_source", "confluence_source", "outline_source"]


def _search_ids(collections_dir: Path, collection: str, query: str) -> list[str]:
    """Return the ranked document ids for ``query`` in one collection."""
    from core.v1.engine.services.search_service import SearchService

    svc = SearchService(collections_path=str(collections_dir))
    results = svc.search(query, max_docs=5, include_matched_chunks=True)
    per_collection = results[collection]
    assert "error" not in per_collection, per_collection
    return [doc["id"] for doc in per_collection["results"]]


@pytest.mark.parametrize("source_name", SOURCES)
def test_cloud_lifecycle(source_name: str, request, local_workspace, build_collection):
    # Warm the engine through the services package first: this is the import
    # entry that resolves the current cold-import cycle (importing the factories
    # or the creator directly fails cold — see .spec/lessons.md).
    import core.v1.engine.services  # noqa: F401
    from core.v1.engine.factories.update_collection_factory import (
        create_collection_updater,
    )
    from core.v1.engine.services.collection_service import clear
    from core.v1.engine.services.inspect_service import InspectService

    src = request.getfixturevalue(source_name)
    collections_dir = local_workspace.collections_dir
    collection = f"{src.reader_type}-net"

    # --- create ----------------------------------------------------------
    build_collection(collections_dir, collection, src.reader, src.converter)
    assert (collections_dir / collection / "manifest.json").exists()

    # --- search: a KNOWN document is the top hit -------------------------
    ranked = _search_ids(collections_dir, collection, src.needle_query)
    assert ranked, "expected at least one search hit"
    assert ranked[0] == src.needle_id, (
        f"expected {src.needle_id!r} as top hit, got {ranked!r}"
    )

    # --- incremental update: a new document becomes searchable -----------
    new_id, new_query = src.add_update()
    updater = create_collection_updater(
        collection_name=collection,
        collections_path=str(collections_dir),
        manifest_connector_factory=lambda manifest: (src.make_reader(), src.converter),
    )
    updater.run()

    post = _search_ids(collections_dir, collection, new_query)
    assert new_id in post, (
        f"newly indexed {new_id!r} should be searchable after update, got {post!r}"
    )

    # --- inspect: reports the grown document count -----------------------
    statuses = InspectService(collections_path=str(collections_dir)).status(
        [collection]
    )
    assert len(statuses) == 1
    assert statuses[0].number_of_documents == 4

    # --- remove: collection is gone from disk ----------------------------
    clear([collection], collections_path=str(collections_dir))
    assert not (collections_dir / collection).exists()
