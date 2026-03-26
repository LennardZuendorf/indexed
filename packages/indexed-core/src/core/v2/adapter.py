"""Adapter converting v1 connector output to LlamaIndex TextNodes.

Bridges the gap between existing connectors (which produce v1 dict format)
and LlamaIndex's node-based indexing. Connectors are NOT modified — this
adapter is the only code that knows about both formats.

The v1 converter output format (per document)::

    {
        "id": str,
        "url": str,
        "modifiedTime": str,
        "text": str,
        "chunks": [{"indexedData": str, "metadata": dict | None}, ...],
    }
"""

from __future__ import annotations

from typing import Any, Iterator, Optional, Protocol

from llama_index.core.schema import TextNode


class PhasedProgress(Protocol):
    """Minimal progress callback protocol (matches v1 PhasedProgressCallback)."""

    def start_phase(self, name: str, total: Optional[int] = None) -> None: ...
    def advance(self, name: str, amount: int = 1) -> None: ...
    def finish_phase(self, name: str) -> None: ...
    def log(self, message: str) -> None: ...


def connector_to_nodes(
    reader: Any,
    converter: Any,
    collection_name: str,
    *,
    progress: Optional[PhasedProgress] = None,
) -> list[TextNode]:
    """Convert connector reader+converter output to LlamaIndex TextNodes.

    Since connectors already produce chunks via indexed-parsing, we create
    TextNodes directly — bypassing LlamaIndex's node parsers.

    Args:
        reader: Connector reader with ``read_all_documents()`` method.
        converter: Connector converter with ``convert(doc)`` method.
        collection_name: Name of the target collection.
        progress: Optional progress callback.

    Returns:
        List of TextNode instances with deterministic IDs.
    """
    nodes: list[TextNode] = []

    if progress:
        progress.start_phase("Fetching documents")

    for raw_doc in reader.read_all_documents():
        converted_docs = converter.convert(raw_doc)
        for converted in _iter_converted(converted_docs):
            doc_nodes = _converted_doc_to_nodes(converted, collection_name)
            nodes.extend(doc_nodes)
            if progress:
                progress.advance("Fetching documents", amount=1)

    if progress:
        progress.finish_phase("Fetching documents")

    return nodes


def _iter_converted(converted: Any) -> Iterator[dict]:
    """Yield converted document dicts, handling both list and single returns."""
    if isinstance(converted, list):
        yield from converted
    else:
        yield converted


def _converted_doc_to_nodes(
    converted: dict,
    collection_name: str,
) -> list[TextNode]:
    """Convert a single v1 converted document dict to TextNodes."""
    doc_id = converted["id"]
    url = converted.get("url", "")
    modified_time = converted.get("modifiedTime", "")
    chunks = converted.get("chunks", [])

    nodes: list[TextNode] = []
    for i, chunk in enumerate(chunks):
        text = chunk.get("indexedData", "")
        if not text:
            continue

        metadata: dict[str, Any] = {
            "source_id": doc_id,
            "url": url,
            "modified_time": modified_time,
            "chunk_index": i,
            "collection_name": collection_name,
        }
        # Merge any chunk-level metadata
        chunk_meta = chunk.get("metadata")
        if chunk_meta and isinstance(chunk_meta, dict):
            metadata.update(chunk_meta)

        node = TextNode(
            text=text,
            metadata=metadata,
            id_=f"{doc_id}__chunk_{i}",
        )
        nodes.append(node)

    return nodes
