"""Search service for semantic search queries."""
from typing import List, Optional
import logging

from index.models.document import SearchResult, Chunk
from index.services.embedding import EmbeddingService
from index.services.storage import StorageService

logger = logging.getLogger(__name__)


class SearchService:
    """Handles semantic search queries.
    
    This service coordinates query embedding, vector search,
    and result formatting.
    """
    
    def __init__(
        self,
        embedding_service: EmbeddingService,
        storage_service: StorageService
    ):
        """Initialize search service.
        
        Args:
            embedding_service: Service for generating query embeddings.
            storage_service: Service for searching vectors.
        """
        self.embedding_service = embedding_service
        self.storage_service = storage_service
        logger.info("SearchService initialized")
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        similarity_threshold: float = 0.0
    ) -> List[SearchResult]:
        """Perform semantic search.
        
        Args:
            query: Search query text.
            top_k: Number of results to return.
            similarity_threshold: Minimum similarity score (0.0-1.0).
            
        Returns:
            List of search results, sorted by relevance.
        """
        logger.info(f"Searching for: '{query[:50]}...' (top_k={top_k})")
        
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)
        logger.debug(f"Generated query embedding with shape {query_embedding.shape}")
        
        # Search vector store
        results = self.storage_service.search(query_embedding, top_k)
        logger.debug(f"Found {len(results)} results from storage")
        
        # Convert to SearchResult objects and filter by threshold
        search_results = []
        for chunk_id, score, metadata in results:
            if score >= similarity_threshold:
                # Reconstruct chunk from metadata
                chunk = self._reconstruct_chunk(chunk_id, metadata)
                search_results.append(SearchResult(
                    chunk=chunk,
                    score=score,
                    document=None  # Document loading can be added later if needed
                ))
        
        logger.info(f"Returning {len(search_results)} results (after threshold filter)")
        return search_results
    
    def _reconstruct_chunk(self, chunk_id: str, metadata: dict) -> Chunk:
        """Reconstruct a Chunk object from stored metadata.
        
        Args:
            chunk_id: Chunk identifier.
            metadata: Stored metadata dictionary.
            
        Returns:
            Reconstructed Chunk object.
        """
        # Extract the content from metadata or use placeholder
        # Note: In a production system, you might want to store the actual
        # content separately or retrieve it from the original source
        content = metadata.get('content', '[Content not available]')
        
        return Chunk(
            id=chunk_id,
            document_id=metadata.get('document_id', metadata.get('filename', 'unknown')),
            content=content,
            index=metadata.get('chunk_index', 0),
            metadata=metadata
        )
