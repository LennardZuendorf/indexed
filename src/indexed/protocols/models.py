from typing import Any, List, Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field


class SourceConfig(BaseModel):
    """Configuration for a document collection source."""

    name: str
    type: Literal[
        "jira", "jiraCloud", "confluence", "confluenceCloud", "localFiles", "outline"
    ]
    base_url_or_path: str = Field(
        ..., description="baseUrl for remote sources OR basePath for files"
    )
    query: Optional[str] = None
    indexer: Optional[str] = None
    reader_opts: dict = Field(
        default_factory=dict, description="Type-specific reader options"
    )


# --- On-disk typed data contracts (foundation/7) -------------------------------
#
# These wrap the v1 collection JSON. The disk format is the compatibility
# boundary for the v2 core swap, so every model round-trips today's camelCase
# JSON byte-stable: fields are declared in on-disk key order, dumped with
# ``by_alias=True``, and optional keys that were absent on disk stay absent.


class IndexerRef(BaseModel):
    """A single entry of the manifest ``indexers`` list (only one today)."""

    model_config = ConfigDict(populate_by_name=True)
    name: str


class ReaderDetails(BaseModel):
    """The manifest ``reader`` block: ``type`` plus per-source camelCase keys.

    ``extra="allow"`` keeps in-the-wild source fields (baseUrl, basePath, query,
    includePatterns, collectionIds, …) untouched across a round-trip.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    type: str


class Manifest(BaseModel):
    """Typed ``manifest.json``. Reads/writes are by model, never by dict key.

    ``extra="allow"`` preserves any unknown top-level key across a round-trip
    (matching the current ``{**existing_manifest, ...}`` merge, which never drops
    keys); today's manifests carry none, so declared-field order is on-disk order.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    collection_name: str = Field(alias="collectionName")
    # createdTime is CREATE-only and additive; collections written before it
    # existed have none and must not gain one on round-trip.
    created_time: Optional[str] = Field(default=None, alias="createdTime")
    updated_time: str = Field(alias="updatedTime")
    last_modified_document_time: str = Field(alias="lastModifiedDocumentTime")
    number_of_documents: int = Field(alias="numberOfDocuments")
    number_of_chunks: int = Field(alias="numberOfChunks")
    reader: ReaderDetails
    indexers: List[IndexerRef]

    @classmethod
    def from_disk(cls, raw: dict) -> "Manifest":
        return cls.model_validate(raw)

    def to_disk(self) -> dict:
        # No global exclude_none: it would drop legitimately-null reader keys.
        # Only the absent-createdTime case is special-cased.
        data = self.model_dump(by_alias=True)
        if self.created_time is None:
            data.pop("createdTime", None)
        return data


class Chunk(BaseModel):
    """One entry of a converted document's ``chunks`` list."""

    model_config = ConfigDict(populate_by_name=True)
    indexed_data: str = Field(alias="indexedData")
    # chunk 0 (the path chunk) and any non-metadata chunk omit this key entirely.
    metadata: Optional[dict] = None

    def to_disk(self) -> dict:
        return self.model_dump(by_alias=True, exclude_none=True)


class ConvertedDocument(BaseModel):
    """Typed ``documents/<id>.json`` — one converted source document."""

    model_config = ConfigDict(populate_by_name=True)
    id: str
    url: str
    modified_time: str = Field(alias="modifiedTime")
    text: str
    chunks: List[Chunk]

    def to_disk(self) -> dict:
        # exclude_none drops each chunk's absent metadata key; every other field
        # is required and non-null, so nothing else is affected.
        return self.model_dump(by_alias=True, exclude_none=True)


class MatchedChunk(BaseModel):
    """One matched chunk inside a search result (runtime; not persisted)."""

    model_config = ConfigDict(populate_by_name=True)
    chunk_number: int = Field(alias="chunkNumber")
    score: float
    content: Optional[Any] = None


class DocumentMatch(BaseModel):
    """One matched document inside a per-collection search result."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    id: str
    url: str
    path: str
    matched_chunks: List[MatchedChunk] = Field(alias="matchedChunks")


class CollectionSearchResult(BaseModel):
    """Per-collection search envelope with an explicit failure channel.

    ``error`` is non-None when the collection failed to search, so per-collection
    failures surface instead of being swallowed as "0 matches".
    """

    model_config = ConfigDict(populate_by_name=True)
    collection_name: str = Field(alias="collectionName")
    indexer_name: str = Field(alias="indexerName")
    results: List[DocumentMatch] = Field(default_factory=list)
    error: Optional[str] = None


class PhasedProgressCallback(Protocol):
    """Protocol for phased progress reporting.

    Supports multi-stage operations where each stage has its own progress
    indicator (spinner or bar). The CLI implements this with Rich Progress;
    the MCP server or tests can use a no-op implementation.

    Stages for indexing: "Loading model", "Fetching documents",
    "Parsing & chunking", "Generating embeddings", "Building FAISS index",
    "Writing to disk".
    """

    def start_phase(self, name: str, total: Optional[int] = None) -> None:
        """Begin a named phase. If total is given, a progress bar is shown;
        otherwise a spinner is used."""
        ...

    def advance(self, name: str, amount: int = 1) -> None:
        """Advance the named phase by amount items."""
        ...

    def finish_phase(self, name: str) -> None:
        """Mark the named phase as complete."""
        ...

    def log(self, message: str) -> None:
        """Display a log message within the progress context."""
        ...


__all__ = [
    "Chunk",
    "CollectionSearchResult",
    "ConvertedDocument",
    "DocumentMatch",
    "IndexerRef",
    "Manifest",
    "MatchedChunk",
    "PhasedProgressCallback",
    "ReaderDetails",
    "SourceConfig",
]
