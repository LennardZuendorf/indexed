"""Indexer registry for dynamic indexer configuration.

This module provides a registry that maps indexer names to their configuration,
enabling dynamic indexer creation without hardcoded switch statements.
"""

from typing import Dict, NamedTuple, List


class IndexerConfig(NamedTuple):
    """Configuration for an indexer.

    Attributes:
        model_name: Full sentence-transformers model name
        embedding_dim: Embedding dimension for FAISS index
        short_name: Short name for the embedding model (used in indexer name)
    """

    model_name: str
    embedding_dim: int
    short_name: str


# Registry of available indexer configurations
# Keys are the short model names, values are full configuration
INDEXER_CONFIGS: Dict[str, IndexerConfig] = {
    "all-MiniLM-L6-v2": IndexerConfig(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        embedding_dim=384,
        short_name="all-MiniLM-L6-v2",
    ),
    "all-mpnet-base-v2": IndexerConfig(
        model_name="sentence-transformers/all-mpnet-base-v2",
        embedding_dim=768,
        short_name="all-mpnet-base-v2",
    ),
    "multi-qa-distilbert-cos-v1": IndexerConfig(
        model_name="sentence-transformers/multi-qa-distilbert-cos-v1",
        embedding_dim=768,
        short_name="multi-qa-distilbert-cos-v1",
    ),
}

# Indexer name prefix pattern
INDEXER_PREFIX = "indexer_FAISS_IndexFlatL2__embeddings_"


def get_indexer_config(indexer_name: str) -> IndexerConfig:
    """Get indexer configuration by full indexer name.

    Args:
        indexer_name: Full indexer name (e.g., "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2")

    Returns:
        IndexerConfig for the specified indexer

    Raises:
        ValueError: If indexer name is not recognized

    Examples:
        >>> config = get_indexer_config("indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2")
        >>> config.model_name
        'sentence-transformers/all-MiniLM-L6-v2'
    """
    # Extract model short name from full indexer name
    short_name = extract_model_name(indexer_name)

    if short_name not in INDEXER_CONFIGS:
        available = list_available_indexers()
        raise ValueError(
            f"Unknown indexer: '{indexer_name}'. "
            f"Available indexers: {', '.join(available)}"
        )

    return INDEXER_CONFIGS[short_name]


def extract_model_name(indexer_name: str) -> str:
    """Extract the model short name from a full indexer name.

    Args:
        indexer_name: Full indexer name

    Returns:
        Model short name (e.g., "all-MiniLM-L6-v2")

    Raises:
        ValueError: If indexer name doesn't match expected pattern
    """
    if not indexer_name.startswith(INDEXER_PREFIX):
        raise ValueError(
            f"Invalid indexer name format: '{indexer_name}'. "
            f"Expected prefix: '{INDEXER_PREFIX}'"
        )

    return indexer_name[len(INDEXER_PREFIX) :]


def build_indexer_name(short_name: str) -> str:
    """Build full indexer name from model short name.

    Args:
        short_name: Model short name (e.g., "all-MiniLM-L6-v2")

    Returns:
        Full indexer name

    Examples:
        >>> build_indexer_name("all-MiniLM-L6-v2")
        'indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2'
    """
    return f"{INDEXER_PREFIX}{short_name}"


def list_available_indexers() -> List[str]:
    """List all available full indexer names.

    Returns:
        List of full indexer names
    """
    return [build_indexer_name(name) for name in INDEXER_CONFIGS.keys()]


def list_available_models() -> List[str]:
    """List all available model short names.

    Returns:
        List of model short names
    """
    return list(INDEXER_CONFIGS.keys())


def is_valid_indexer(indexer_name: str) -> bool:
    """Check if an indexer name is valid.

    Args:
        indexer_name: Full indexer name to check

    Returns:
        True if the indexer is registered, False otherwise
    """
    try:
        get_indexer_config(indexer_name)
        return True
    except ValueError:
        return False
