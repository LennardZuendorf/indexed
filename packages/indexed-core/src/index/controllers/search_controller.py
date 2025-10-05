"""Search controller for high-level search operations."""
from typing import List, Dict, Any
import logging

from index.models.document import SearchResult
from index.services.search import SearchService

logger = logging.getLogger(__name__)


class SearchController:
    """High-level controller for search operations.
    
    This controller provides the main API for semantic search,
    delegating to the search service.
    """
    
    def __init__(self, search_service: SearchService):
        """Initialize search controller.
        
        Args:
            search_service: Service for search operations.
        """
        self.search_service = search_service
        logger.info("SearchController initialized")
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        similarity_threshold: float = 0.0
    ) -> List[SearchResult]:
        """Execute semantic search.
        
        Args:
            query: Search query text.
            top_k: Number of results to return.
            similarity_threshold: Minimum similarity score.
            
        Returns:
            List of search results, sorted by relevance.
        """
        logger.info(f"Search request: '{query[:50]}...'")
        
        results = self.search_service.search(
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold
        )
        
        logger.info(f"Returned {len(results)} results")
        return results
    
    def search_with_filters(
        self,
        query: str,
        filters: Dict[str, Any],
        top_k: int = 10,
        similarity_threshold: float = 0.0
    ) -> List[SearchResult]:
        """Search with metadata filters.
        
        Note: This is a placeholder for future implementation.
        Currently just performs regular search.
        
        Args:
            query: Search query text.
            filters: Metadata filters to apply.
            top_k: Number of results to return.
            similarity_threshold: Minimum similarity score.
            
        Returns:
            List of filtered search results.
        """
        logger.info(f"Search with filters: '{query[:50]}...', filters={filters}")
        
        # Perform search
        results = self.search_service.search(
            query=query,
            top_k=top_k * 2,  # Get more results for filtering
            similarity_threshold=similarity_threshold
        )
        
        # Apply filters
        filtered_results = []
        for result in results:
            if self._matches_filters(result, filters):
                filtered_results.append(result)
                if len(filtered_results) >= top_k:
                    break
        
        logger.info(f"Returned {len(filtered_results)} filtered results")
        return filtered_results
    
    def _matches_filters(self, result: SearchResult, filters: Dict[str, Any]) -> bool:
        """Check if a result matches the given filters.
        
        Args:
            result: Search result to check.
            filters: Filters to apply.
            
        Returns:
            True if result matches all filters.
        """
        for key, value in filters.items():
            if key not in result.chunk.metadata:
                return False
            if result.chunk.metadata[key] != value:
                return False
        return True
