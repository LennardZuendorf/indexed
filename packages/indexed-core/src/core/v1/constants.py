"""Core v1 constants.

Centralized constants for the indexed-core package to avoid duplication
and ensure consistency across CLI and library usage.
"""

# Default indexer used when no specific indexer is configured
# Uses FAISS with IndexFlatL2 and all-MiniLM-L6-v2 embeddings
DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

# Available indexer names (for reference/validation)
AVAILABLE_INDEXERS = [
    "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
    "indexer_FAISS_IndexFlatL2__embeddings_all-mpnet-base-v2",
    "indexer_FAISS_IndexFlatL2__embeddings_multi-qa-distilbert-cos-v1",
]
