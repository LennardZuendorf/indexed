"""Indexer registry for building and managing indexer names."""


def build_indexer_name(model_name: str) -> str:
    """Build a standardized indexer name from an embedding model name.

    Args:
        model_name: The embedding model name (e.g., "all-MiniLM-L6-v2")

    Returns:
        Standardized indexer name in format: indexer_FAISS_IndexFlatL2__embeddings_{model_name}

    Examples:
        >>> build_indexer_name("all-MiniLM-L6-v2")
        'indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2'
    """
    # Normalize model name (handle variations)
    normalized_model = model_name.replace("sentence-transformers/", "")
    return f"indexer_FAISS_IndexFlatL2__embeddings_{normalized_model}"
