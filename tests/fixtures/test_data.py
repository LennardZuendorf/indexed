"""Test data utilities and generators.

This module provides utilities for generating test data,
including vectors, embeddings, and synthetic documents.
"""

import numpy as np
from typing import List, Tuple


def generate_random_vectors(
    count: int,
    dimension: int = 384,
    seed: int = 42
) -> np.ndarray:
    """Generate random embedding vectors for testing.
    
    Args:
        count: Number of vectors to generate
        dimension: Dimension of each vector
        seed: Random seed for reproducibility
        
    Returns:
        numpy array of shape (count, dimension)
    """
    np.random.seed(seed)
    return np.random.rand(count, dimension).astype('float32')


def generate_vector_ids(count: int, prefix: str = "chunk") -> List[str]:
    """Generate vector IDs for testing.
    
    Args:
        count: Number of IDs to generate
        prefix: Prefix for each ID
        
    Returns:
        List of ID strings
    """
    return [f"{prefix}-{i:04d}" for i in range(count)]


def generate_test_chunks(
    count: int
) -> List[Tuple[str, str, dict]]:
    """Generate test document chunks.
    
    Args:
        count: Number of chunks to generate
        
    Returns:
        List of tuples (chunk_id, text, metadata)
    """
    chunks = []
    for i in range(count):
        chunk_id = f"chunk-{i:04d}"
        text = f"This is test chunk {i} containing sample text about testing and integration."
        metadata = {
            "document_id": f"doc-{i // 3}",
            "chunk_index": i % 3,
            "source": "test"
        }
        chunks.append((chunk_id, text, metadata))
    
    return chunks


def create_mock_collection_manifest() -> dict:
    """Create a mock collection manifest.
    
    Returns:
        Dictionary representing collection metadata
    """
    return {
        "name": "test-collection",
        "type": "localFiles",
        "created_at": "2025-01-01T00:00:00Z",
        "document_count": 10,
        "chunk_count": 30,
        "indexer": "test-indexer",
        "config": {
            "path": "/tmp/test-docs",
            "include_patterns": [".*\\.md$"],
            "exclude_patterns": []
        }
    }

