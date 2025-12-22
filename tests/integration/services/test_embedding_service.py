"""Integration tests for EmbeddingService.

Tests sentence-transformers embedding service with model loading,
single text embedding, and batch processing.
"""

import pytest
import numpy as np
from core.v1.engine.service.embedding import EmbeddingService


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_initialization():
    """Test EmbeddingService initialization and model loading."""
    service = EmbeddingService(
        model_name="all-MiniLM-L6-v2",
        batch_size=16
    )
    
    # Verify model is loaded
    assert service.model is not None
    assert service.model_name == "all-MiniLM-L6-v2"
    assert service.batch_size == 16
    
    # Verify dimension
    assert service.dimension == 384  # all-MiniLM-L6-v2 has 384 dimensions


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_single_text():
    """Test embedding a single text."""
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    text = "This is a test sentence about authentication methods."
    
    embedding = service.embed_text(text)
    
    # Verify embedding structure
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (384,)  # all-MiniLM-L6-v2 dimension
    assert embedding.dtype == np.float32


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_batch():
    """Test embedding multiple texts in batch."""
    service = EmbeddingService(
        model_name="all-MiniLM-L6-v2",
        batch_size=4
    )
    
    texts = [
        "First document about authentication",
        "Second document about API testing",
        "Third document about deployment",
        "Fourth document about monitoring",
        "Fifth document about security"
    ]
    
    embeddings = service.embed_batch(texts, show_progress=False)
    
    # Verify embeddings structure
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (5, 384)  # 5 texts, 384 dimensions
    assert embeddings.dtype == np.float32


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_empty_batch():
    """Test embedding empty batch."""
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    embeddings = service.embed_batch([])
    
    # Should return empty array with correct shape
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (0, 384)


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_similarity():
    """Test that similar texts produce similar embeddings."""
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    # Similar texts
    text1 = "OAuth authentication and JWT tokens"
    text2 = "OAuth and JWT token authentication"
    
    # Dissimilar text
    text3 = "Docker container deployment strategies"
    
    emb1 = service.embed_text(text1)
    emb2 = service.embed_text(text2)
    emb3 = service.embed_text(text3)
    
    # Calculate cosine similarity
    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    sim_similar = cosine_similarity(emb1, emb2)
    sim_different = cosine_similarity(emb1, emb3)
    
    # Similar texts should have higher similarity
    assert sim_similar > sim_different
    assert sim_similar > 0.7  # Should be quite similar


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_consistency():
    """Test that same text produces same embedding."""
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    text = "Consistent text for testing embedding reproducibility"
    
    emb1 = service.embed_text(text)
    emb2 = service.embed_text(text)
    
    # Should be identical (or very close due to floating point)
    np.testing.assert_allclose(emb1, emb2, rtol=1e-5)


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_batch_size():
    """Test embedding with different batch sizes."""
    texts = [f"Test document {i} with sample content" for i in range(20)]
    
    # Test with different batch sizes
    for batch_size in [4, 8, 16]:
        service = EmbeddingService(
            model_name="all-MiniLM-L6-v2",
            batch_size=batch_size
        )
        
        embeddings = service.embed_batch(texts, show_progress=False)
        
        assert embeddings.shape == (20, 384)


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_long_text():
    """Test embedding longer text."""
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    # Create a longer text
    long_text = " ".join([
        "This is a longer test document.",
        "It contains multiple sentences to test how the model handles longer inputs.",
        "The embedding service should handle this without issues.",
        "Testing with authentication, API integration, and deployment topics.",
        "More content to ensure the text is sufficiently long for testing."
    ])
    
    embedding = service.embed_text(long_text)
    
    # Verify embedding is generated correctly
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (384,)


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_special_characters():
    """Test embedding text with special characters."""
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    text = "Test with special chars: @#$%^&*()! and unicode: café, naïve, Москва"
    
    embedding = service.embed_text(text)
    
    # Should handle special characters without error
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (384,)


@pytest.mark.integration
@pytest.mark.slow
def test_embedding_service_dimension_property():
    """Test the dimension property."""
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    dim = service.dimension
    
    assert isinstance(dim, int)
    assert dim == 384  # all-MiniLM-L6-v2 dimension
    
    # Verify dimension matches actual embedding
    text = "Test text"
    embedding = service.embed_text(text)
    assert embedding.shape[0] == dim

