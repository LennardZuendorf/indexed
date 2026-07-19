"""Shared fakes/helpers for the core-v2/2c engine tests (import, not a fixture).

Imported absolutely (``from tests.unit.indexed.core.v2._engine_helpers import
...``) — the v2 test dir is a package (``__init__.py`` present), matching the
rest of the tests tree. Most structural tests are MODEL-FREE: they patch
``build_embed_model`` at its source with a LlamaIndex ``MockEmbedding`` so no
model download/load is needed.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, Optional


def make_doc(
    doc_id: str,
    chunk_texts: List[str],
    *,
    url: str = "u",
    modified_time: str = "2026-01-10T00:00:00+00:00",
) -> dict:
    """An on-disk-shaped ConvertedDocument dict (what converters emit today)."""
    return {
        "id": doc_id,
        "url": url,
        "modifiedTime": modified_time,
        "text": " ".join(chunk_texts),
        "chunks": [{"indexedData": t} for t in chunk_texts],
    }


class _FakeReader:
    def __init__(self, docs: List[dict], reader_details: Optional[dict]) -> None:
        self._docs = docs
        self._reader_details = reader_details or {
            "type": "localFiles",
            "basePath": "/corpus",
        }

    def get_number_of_documents(self) -> int:
        return len(self._docs)

    def read_all_documents(self) -> Iterator[dict]:
        yield from self._docs

    def get_reader_details(self) -> dict:
        return dict(self._reader_details)


class _FakeConverter:
    def convert(self, doc: dict) -> List[dict]:
        return [doc]


class _FakeConnector:
    def __init__(self, docs: List[dict], reader_details: Optional[dict]) -> None:
        self.reader = _FakeReader(docs, reader_details)
        self.converter = _FakeConverter()


def make_connector_factory(
    docs: List[dict], reader_details: Optional[dict] = None
) -> Callable[[Any], _FakeConnector]:
    """A one-shot ``connector_factory`` yielding a fake connector over ``docs``."""
    return lambda cfg: _FakeConnector(list(docs), reader_details)


def make_update_manifest_factory(
    docs: List[dict],
    *,
    deletions: Optional[List[str]] = None,
    post_run: Optional[Callable[[], None]] = None,
) -> Callable[[Any, str], Any]:
    """A ``manifest_factory`` yielding a ``ConnectorRun`` over ``docs``.

    Mirrors composition's ``make_manifest_factory``: the v2 update calls this
    with ``(manifest, storage_path)`` and reads ``run.reader/converter/
    deletions/post_run`` — exactly what the files connector's ``from_manifest``
    returns. The fake reader yields only ``docs`` (the connector's job is to hand
    back the new/changed documents), so unchanged docs are simply absent here.
    """
    from indexed.protocols.connectors import ConnectorRun

    def factory(manifest: Any, storage_path: str) -> ConnectorRun:
        return ConnectorRun(
            _FakeReader(list(docs), None),
            _FakeConverter(),
            list(deletions or []),
            post_run,
        )

    return factory


@contextmanager
def recording_embedding(embed_dim: int = 8) -> Iterator[List[str]]:
    """Patch ``build_embed_model`` with a MockEmbedding that RECORDS embedded texts.

    Yields the shared list of texts passed to ``_get_text_embedding`` (document
    chunk texts — query embeddings go through ``_get_query_embedding`` and are
    NOT recorded), so a test can prove incrementality: after an update, the list
    holds EXACTLY the changed/new chunk texts and none of the unchanged ones.
    Clear the list (``embedded.clear()``) between create and update to isolate
    the update's embeddings.
    """
    from unittest.mock import patch

    from llama_index.core.embeddings import MockEmbedding

    embedded: List[str] = []

    class _Recording(MockEmbedding):
        def _get_text_embedding(self, text: str) -> List[float]:
            embedded.append(text)
            return super()._get_text_embedding(text)

    with patch(
        "indexed.core.v2.embedding.local.build_embed_model",
        return_value=_Recording(embed_dim=embed_dim),
    ):
        yield embedded


@contextmanager
def mock_embedding(embed_dim: int = 8) -> Iterator[None]:
    """Patch ``build_embed_model`` at its source with a MockEmbedding.

    Both ``ingestion`` and ``retrieval`` import ``build_embed_model`` from
    ``embedding.local`` function-locally, so patching the source covers both.
    """
    from unittest.mock import patch

    from llama_index.core.embeddings import MockEmbedding

    with patch(
        "indexed.core.v2.embedding.local.build_embed_model",
        return_value=MockEmbedding(embed_dim=embed_dim),
    ):
        yield
