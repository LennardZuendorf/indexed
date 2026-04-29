"""Factory for creating and loading FAISS indexers.

This module provides factory functions for creating new indexers and loading
existing ones from disk. It uses the indexer registry for configuration.
"""

import logging
from typing import Optional

from .indexer_registry import get_indexer_config, is_auto_indexer

logger = logging.getLogger(__name__)


def create_indexer(indexer_name: str):
    """Create a new FAISS indexer with the specified configuration.

    Args:
        indexer_name: Full indexer name (e.g., "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
                      or "indexer_FAISS_Auto__embeddings_all-MiniLM-L6-v2")

    Returns:
        Configured FaissIndexer or FaissAutoIndexer instance

    Raises:
        ValueError: If indexer_name is not recognized

    Examples:
        >>> indexer = create_indexer("indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2")
        >>> indexer.index_texts([0, 1], ["Hello world", "Test document"])
    """
    from .embeddings.sentence_embeder import SentenceEmbedder

    config = get_indexer_config(indexer_name)
    embedder = SentenceEmbedder(model_name=config.model_name)

    if is_auto_indexer(indexer_name):
        from .indexers.faiss_auto_indexer import FaissAutoIndexer

        return FaissAutoIndexer(indexer_name, embedder)

    from .indexers.faiss_indexer import FaissIndexer

    return FaissIndexer(indexer_name, embedder)


def load_indexer(
    indexer_name: str,
    collection_name: str,
    persister,
    serialized_index: Optional[bytes] = None,
):
    """Load an existing FAISS indexer from disk.

    Prefers native FAISS file format with memory-mapped I/O for fast loading.
    Falls back to legacy pickle format for backward compatibility.

    Args:
        indexer_name: Full indexer name
        collection_name: Name of the collection containing the index
        persister: DiskPersister instance for reading files
        serialized_index: Optional pre-loaded serialized index bytes

    Returns:
        FaissIndexer loaded from disk

    Raises:
        ValueError: If indexer_name is not recognized
        FileNotFoundError: If the index file doesn't exist
    """
    from .embeddings.sentence_embeder import SentenceEmbedder

    config = get_indexer_config(indexer_name)
    embedder = SentenceEmbedder(model_name=config.model_name)

    faiss_index = None

    if serialized_index is None:
        index_base = f"{collection_name}/indexes/{indexer_name}"
        native_path = f"{index_base}/indexer.faiss"
        legacy_path = f"{index_base}/indexer"

        # Prefer native FAISS format (memory-mapped, fast)
        if persister.is_path_exists(native_path):
            faiss_index = persister.read_faiss_index(native_path, mmap=True)
            logger.debug(f"Loaded FAISS index via mmap: {native_path}")
        elif persister.is_path_exists(legacy_path):
            # Fall back to legacy pickle format
            serialized_index = persister.read_bin_file(legacy_path)
            logger.debug(f"Loaded FAISS index via legacy pickle: {legacy_path}")
        else:
            raise FileNotFoundError(
                f"No FAISS index found at '{native_path}' or '{legacy_path}'"
            )

    if is_auto_indexer(indexer_name):
        from .indexers.faiss_auto_indexer import FaissAutoIndexer

        return FaissAutoIndexer(
            indexer_name,
            embedder,
            serialized_index=serialized_index,
            faiss_index=faiss_index,
        )

    from .indexers.faiss_indexer import FaissIndexer

    return FaissIndexer(
        indexer_name,
        embedder,
        serialized_index=serialized_index,
        faiss_index=faiss_index,
    )
