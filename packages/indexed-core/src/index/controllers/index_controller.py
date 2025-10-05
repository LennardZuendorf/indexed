"""Index controller for high-level indexing operations."""
from typing import List, Dict, Any
import logging
import time

from index.services.indexing import IndexingService
from index.services.storage import StorageService

logger = logging.getLogger(__name__)


class IndexController:
    """High-level controller for indexing operations.
    
    This controller provides the main API for index management,
    coordinating between indexing and storage services.
    """
    
    def __init__(
        self,
        indexing_service: IndexingService,
        storage_service: StorageService
    ):
        """Initialize index controller.
        
        Args:
            indexing_service: Service for document indexing.
            storage_service: Service for storage management.
        """
        self.indexing_service = indexing_service
        self.storage_service = storage_service
        logger.info("IndexController initialized")
    
    def create_index(self, sources: List[str]) -> Dict[str, Any]:
        """Create a new index from sources.
        
        Args:
            sources: List of source paths to index.
            
        Returns:
            Statistics about the indexing operation.
        """
        logger.info(f"Creating index from {len(sources)} sources")
        start_time = time.time()
        
        total_stats = {
            "documents_processed": 0,
            "chunks_created": 0,
            "chunks_indexed": 0,
            "sources": sources,
            "time_taken": 0,
        }
        
        # Index each source
        for source in sources:
            try:
                stats = self.indexing_service.index_source(source)
                total_stats["documents_processed"] += stats["documents_processed"]
                total_stats["chunks_created"] += stats["chunks_created"]
                total_stats["chunks_indexed"] += stats["chunks_indexed"]
            except Exception as e:
                logger.error(f"Error indexing source {source}: {e}")
                continue
        
        total_stats["time_taken"] = time.time() - start_time
        
        logger.info(
            f"Index created: {total_stats['documents_processed']} documents, "
            f"{total_stats['chunks_indexed']} chunks in {total_stats['time_taken']:.2f}s"
        )
        
        return total_stats
    
    def update_index(self, sources: List[str]) -> Dict[str, Any]:
        """Incrementally update existing index.
        
        Currently performs the same operation as create_index since we
        don't track which files have already been indexed. Future improvement
        could add change tracking.
        
        Args:
            sources: List of source paths to index.
            
        Returns:
            Statistics about the indexing operation.
        """
        logger.info(f"Updating index from {len(sources)} sources")
        return self.create_index(sources)
    
    def rebuild_index(self, sources: List[str]) -> Dict[str, Any]:
        """Completely rebuild index from scratch.
        
        Args:
            sources: List of source paths to index.
            
        Returns:
            Statistics about the indexing operation.
        """
        logger.info(f"Rebuilding index from {len(sources)} sources")
        
        # Clear existing index
        self.storage_service.clear()
        logger.info("Cleared existing index")
        
        # Rebuild
        return self.create_index(sources)
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get current index statistics.
        
        Returns:
            Dictionary of index statistics.
        """
        stats = self.storage_service.get_stats()
        logger.debug(f"Index stats: {stats}")
        return stats
