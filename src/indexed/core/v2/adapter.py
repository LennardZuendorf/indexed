"""ConvertedDocument -> LlamaIndex TextNode[] adapter (core-v2/2a).

Connectors/parsing never import LlamaIndex (tech.md "Adapter"); this is the
one place a converted-document dict crosses into LlamaIndex's node model, and
even here the import is function-local so importing this module stays cheap.

Ref-doc linkage (verified against the installed llama-index-core==0.14.23,
see task report): ``TextNode.ref_doc_id`` is a READ-ONLY property derived
from ``relationships[NodeRelationship.SOURCE]`` — it has no setter. The
canonical way to record the upsert/delete key that
``KVDocumentStore.delete_ref_doc``/``add_documents`` key on is:

    node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=doc_id)

which then makes ``node.ref_doc_id == doc_id`` for free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union

from indexed.protocols.models import ConvertedDocument

if TYPE_CHECKING:
    from llama_index.core.schema import TextNode


def to_nodes(
    doc: Union[dict[str, Any], ConvertedDocument], collection: str
) -> list["TextNode"]:
    """Convert one ConvertedDocument (on-disk dict shape) into TextNodes.

    ``doc`` is the by_alias on-disk shape (``id``/``url``/``modifiedTime``/
    ``chunks``); a ``ConvertedDocument`` model is also accepted for
    convenience and normalized via ``.to_disk()``. Node id
    ``f"{doc['id']}::chunk_{i}"`` is deterministic and stable; an empty
    ``chunks`` list returns ``[]``.
    """
    from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

    if isinstance(doc, ConvertedDocument):
        doc = doc.to_disk()

    doc_id = doc["id"]
    nodes: list[TextNode] = []
    for i, chunk in enumerate(doc.get("chunks", [])):
        node = TextNode(text=chunk["indexedData"], id_=f"{doc_id}::chunk_{i}")
        node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=doc_id)
        node.metadata = {
            "source_id": doc_id,
            "url": doc["url"],
            "modified_time": doc.get("modifiedTime"),
            "chunk_number": i,
            "collection": collection,
            **(chunk.get("metadata") or {}),
        }
        nodes.append(node)
    return nodes


__all__ = ["to_nodes"]
