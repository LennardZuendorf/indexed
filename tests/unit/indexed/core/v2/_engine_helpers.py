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
