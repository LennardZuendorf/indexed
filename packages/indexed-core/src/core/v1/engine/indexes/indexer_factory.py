"""Factory for creating and loading FAISS indexers.

This module provides factory functions for creating new indexers and loading
existing ones from disk. It uses the indexer registry for configuration.
"""

from typing import Optional

from .indexers.faiss_indexer import FaissIndexer
from .embeddings.sentence_embeder import SentenceEmbedder
from .indexer_registry import get_indexer_config


def create_indexer(indexer_name: str) -> FaissIndexer:
    """Create a new FAISS indexer with the specified configuration.
    
    Args:
        indexer_name: Full indexer name (e.g., "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2")
        
    Returns:
        Configured FaissIndexer instance
        
    Raises:
        ValueError: If indexer_name is not recognized
        
    Examples:
        >>> indexer = create_indexer("indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2")
        >>> indexer.index_texts([0, 1], ["Hello world", "Test document"])
    """
    config = get_indexer_config(indexer_name)
    
    embedder = SentenceEmbedder(model_name=config.model_name)
    
    return FaissIndexer(indexer_name, embedder)


def load_indexer(
    indexer_name: str,
    collection_name: str,
    persister,
    serialized_index: Optional[bytes] = None,
) -> FaissIndexer:
    """Load an existing FAISS indexer from disk.
    
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
        
    Examples:
        >>> persister = DiskPersister(base_path="./data/collections")
        >>> indexer = load_indexer(
        ...     "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
        ...     "my-collection",
        ...     persister
        ... )
    """
    config = get_indexer_config(indexer_name)
    
    # Load serialized index from disk if not provided
    if serialized_index is None:
        serialized_index = persister.read_bin_file(
            f"{collection_name}/indexes/{indexer_name}/indexer"
        )
    
    embedder = SentenceEmbedder(model_name=config.model_name)
    
    return FaissIndexer(indexer_name, embedder, serialized_index)
