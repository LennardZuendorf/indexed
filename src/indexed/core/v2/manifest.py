"""V2 manifest model + IO (core-v2/2a).

Same filename (``manifest.json``) as v1, a superset shape: a ``version``
marker plus an ``engine`` block (embedding/store/score-kind/version pins)
replacing v1's ``indexers[]`` list. The ``reader`` block stays byte-identical
to v1's so the existing ``manifest_factory``/``from_manifest`` update path
works unchanged for v2 (tech.md "V2 manifest").

No LlamaIndex import here — only ``importlib.metadata`` string lookups.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from indexed.protocols.models import ReaderDetails


def _package_version(name: str) -> str:
    """Resolve an installed distribution's version, or ``"unknown"``.

    Robust to running outside an installed dist (e.g. a bare source checkout)
    per ``.spec/features/core-v2/tech.md`` "Dependency pinning".
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def indexed_version() -> str:
    """The installed ``indexed-sh`` distribution version."""
    return _package_version("indexed-sh")


def llama_index_core_version() -> str:
    """The installed ``llama-index-core`` distribution version."""
    return _package_version("llama-index-core")


class V2EmbeddingInfo(BaseModel):
    """``engine.embedding`` — the model that produced this collection's vectors."""

    model_config = ConfigDict(populate_by_name=True)
    provider: str
    model: str
    dimension: int


class V2EngineBlock(BaseModel):
    """``engine`` — replaces v1's ``indexers[]`` multi-indexer plumbing."""

    model_config = ConfigDict(populate_by_name=True)
    embedding: V2EmbeddingInfo
    vector_store: str = Field(alias="vectorStore")
    score_kind: str = Field(alias="scoreKind")
    llama_index_core_version: str = Field(alias="llamaIndexCoreVersion")
    indexed_version: str = Field(alias="indexedVersion")


class V2Manifest(BaseModel):
    """Typed v2 ``manifest.json``. Reads/writes are by model, never by dict key.

    Fields are declared in on-disk key order so ``model_dump(by_alias=True)``
    round-trips byte-stable (``.spec/lessons.md``); ``extra="allow"`` lets
    future top-level keys pass through untouched.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    version: Literal["2"] = "2"
    collection_name: str = Field(alias="collectionName")
    # createdTime is CREATE-only; absent on round-trip when unset.
    created_time: Optional[str] = Field(default=None, alias="createdTime")
    updated_time: str = Field(alias="updatedTime")
    last_modified_document_time: str = Field(alias="lastModifiedDocumentTime")
    number_of_documents: int = Field(alias="numberOfDocuments")
    number_of_chunks: int = Field(alias="numberOfChunks")
    reader: ReaderDetails
    engine: V2EngineBlock

    @classmethod
    def from_disk(cls, raw: dict) -> "V2Manifest":
        return cls.model_validate(raw)

    def to_disk(self) -> dict:
        data = self.model_dump(by_alias=True)
        if self.created_time is None:
            data.pop("createdTime", None)
        return data

    @classmethod
    def new(
        cls,
        *,
        collection_name: str,
        reader: ReaderDetails,
        embedding_model: str,
        dimension: int,
        created_time: str,
        updated_time: str,
        last_modified_document_time: str,
        number_of_documents: int = 0,
        number_of_chunks: int = 0,
        embedding_provider: str = "local",
        vector_store: str = "simple",
        score_kind: str = "cosine",
    ) -> "V2Manifest":
        """Build a fresh v2 manifest at create time (used by core-v2/2c).

        Records the currently-installed ``llamaIndexCoreVersion`` /
        ``indexedVersion`` (rebuild-on-mismatch guard, tech.md).
        """
        # Keyword args use the on-disk ALIAS names (not the snake_case field
        # names) even though ``populate_by_name=True`` accepts either at
        # runtime — ty's pydantic model synthesis only recognizes the alias
        # form of the constructor (verified: a bare field-name kwarg trips
        # ty's ``missing-argument`` on an aliased required field).
        engine = V2EngineBlock(
            embedding=V2EmbeddingInfo(
                provider=embedding_provider, model=embedding_model, dimension=dimension
            ),
            vectorStore=vector_store,
            scoreKind=score_kind,
            llamaIndexCoreVersion=llama_index_core_version(),
            indexedVersion=indexed_version(),
        )
        return cls(
            collectionName=collection_name,
            createdTime=created_time,
            updatedTime=updated_time,
            lastModifiedDocumentTime=last_modified_document_time,
            numberOfDocuments=number_of_documents,
            numberOfChunks=number_of_chunks,
            reader=reader,
            engine=engine,
        )


__all__ = [
    "V2EmbeddingInfo",
    "V2EngineBlock",
    "V2Manifest",
    "indexed_version",
    "llama_index_core_version",
]
