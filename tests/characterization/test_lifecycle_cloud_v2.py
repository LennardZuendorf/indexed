"""Characterization: full cloud-source lifecycle behavior net on the v2 engine
(core-v2/8, R4 surface parity).

Mirrors ``tests/characterization/test_lifecycle_cloud.py`` STYLE — real
reader+converter with the network stubbed at the ``read_documents`` boundary,
real embeddings, KNOWN-HIT search assertions — but drives the **v2** engine
(``indexed.core.v2.services``) instead of v1. For each cloud connector
(jira / confluence / outline) it walks the whole lifecycle:

    create -> search (known doc is the top hit) -> incremental update
    (new doc becomes searchable) -> inspect (doc count) -> remove (gone).

This is the R4 cloud-parity net; it runs GREEN alongside v1's UNTOUCHED cloud
net (``test_lifecycle_cloud.py``) — the two prove the same behavior over the
two engines on the same fixtures.
"""

from __future__ import annotations

import pytest

from tests.conftest import model_available

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

SOURCES = ["jira_source", "confluence_source", "outline_source"]


def _connector_factory(reader, converter):
    """A one-shot v2 ``connector_factory`` yielding the fixture reader+converter.

    v2's ``ingestion.create`` reads ``connector.reader``/``connector.converter``
    off whatever the factory returns (exactly the ``protocols`` seam v1 drives),
    so a plain object carrying the two is all it needs — the ``cfg`` is unused
    because the stub reader is already bound to its fixture HTTP.
    """
    from types import SimpleNamespace

    return lambda cfg: SimpleNamespace(reader=reader, converter=converter)


def _search_ids(collections_dir, collection: str, query: str) -> list[str]:
    """Return the ranked document ids for ``query`` in one v2 collection."""
    from indexed.core.v2 import services

    results = services.search(
        query,
        collections_path=str(collections_dir),
        max_docs=5,
        include_matched_chunks=True,
    )
    per_collection = results[collection]
    assert "error" not in per_collection, per_collection
    return [doc["id"] for doc in per_collection["results"]]


@pytest.mark.parametrize("source_name", SOURCES)
def test_cloud_lifecycle_v2(source_name: str, request, local_workspace):
    # Warm the v2 engine through its services package first — same cold-import
    # discipline the v1 cloud net uses (``import ...v1.engine.services``): a test
    # that touches the engine outside the CLI warms the package import so the
    # (function-local) LlamaIndex imports resolve in the right order.
    from indexed.core.v2 import services
    from indexed.protocols import ConnectorRun, SourceConfig

    src = request.getfixturevalue(source_name)
    collections_dir = local_workspace.collections_dir
    collection = f"{src.reader_type}-net-v2"
    cfg = SourceConfig(
        name=collection,
        type=src.reader_type,
        base_url_or_path="https://stub.example.com",
    )

    # --- create (v2 engine) ----------------------------------------------
    services.create(
        [cfg],
        collections_path=str(collections_dir),
        connector_factory=_connector_factory(src.reader, src.converter),
    )
    manifest_path = collections_dir / collection / "manifest.json"
    assert manifest_path.exists()

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["version"] == "2"
    assert manifest["engine"]["vectorStore"] == "simple"
    assert manifest["reader"]["type"] == src.reader_type

    # --- search: a KNOWN document is the top hit -------------------------
    ranked = _search_ids(collections_dir, collection, src.needle_query)
    assert ranked, "expected at least one search hit"
    assert ranked[0] == src.needle_id, (
        f"expected {src.needle_id!r} as top hit, got {ranked!r}"
    )

    # --- incremental update: a new document becomes searchable -----------
    new_id, new_query = src.add_update()
    services.update(
        [cfg],
        collections_path=str(collections_dir),
        manifest_factory=lambda manifest_obj, storage_path: ConnectorRun(
            src.make_reader(), src.converter, [], None
        ),
    )

    post = _search_ids(collections_dir, collection, new_query)
    assert new_id in post, (
        f"newly indexed {new_id!r} should be searchable after update, got {post!r}"
    )

    # --- inspect: reports the grown document count -----------------------
    statuses = services.status([collection], collections_path=str(collections_dir))
    assert len(statuses) == 1
    assert statuses[0]["number_of_documents"] == 4

    # --- remove: collection is gone from disk ----------------------------
    services.clear([collection], collections_path=str(collections_dir))
    assert not (collections_dir / collection).exists()
