"""Service factory for dependency injection.

This module provides the composition root for the application,
instantiating all services and controllers with proper dependency injection.
"""
from typing import Tuple
import logging

from indexed_core.config.models import IndexedConfig
from indexed_core.services.embedding import EmbeddingService
from indexed_core.services.storage import StorageService
from indexed_core.services.indexing import IndexingService
from indexed_core.services.search import SearchService
from indexed_core.connectors.filesystem import FileSystemConnector
from indexed_core.controllers.index_controller import IndexController
from indexed_core.controllers.search_controller import SearchController

logger = logging.getLogger(__name__)


class ServiceFactory:
    """Factory for creating services from configuration.
    
    This class acts as the composition root, responsible for:
    1. Reading configuration
    2. Instantiating services with dependencies
    3. Wiring up the dependency graph
    4. Returning fully configured controllers
    """
    
    @staticmethod
    def create_from_config(config: IndexedConfig) -> Tuple[IndexController, SearchController]:
        """Create all services and controllers from configuration.
        
        This is the main entry point for bootstrapping the application.
        It follows these steps:
        1. Create infrastructure services (embedding, storage)
        2. Create connectors
        3. Create business logic services (indexing, search)
        4. Create controllers
        
        Args:
            config: Validated configuration object.
            
        Returns:
            Tuple of (IndexController, SearchController) ready to use.
        """
        logger.info("ServiceFactory: Creating services from configuration")
        
        # 1. Create EmbeddingService
        logger.debug(f"Creating EmbeddingService with model: {config.embedding.model_name}")
        embedding_service = EmbeddingService(
            model_name=config.embedding.model_name,
            device=config.embedding.device,
            batch_size=config.embedding.batch_size
        )
        
        # 2. Create StorageService
        logger.debug(f"Creating StorageService with type: {config.vector_store.type}")
        storage_service = StorageService(
            dimension=embedding_service.dimension,  # Get dimension from model
            index_type=config.vector_store.index_type,
            persistence_path=config.vector_store.persistence_path
        )
        
        # 3. Create connectors
        connectors = []
        if config.connectors.filesystem_enabled:
            logger.debug("Creating FileSystemConnector")
            connectors.append(FileSystemConnector(
                include_patterns=config.indexing.include_patterns,
                exclude_patterns=config.indexing.exclude_patterns
            ))
        
        if not connectors:
            logger.warning("No connectors enabled! At least one connector is required.")
        
        # 4. Create IndexingService
        logger.debug("Creating IndexingService")
        indexing_service = IndexingService(
            connectors=connectors,
            embedding_service=embedding_service,
            storage_service=storage_service,
            chunk_size=config.indexing.chunk_size,
            chunk_overlap=config.indexing.chunk_overlap
        )
        
        # 5. Create SearchService
        logger.debug("Creating SearchService")
        search_service = SearchService(
            embedding_service=embedding_service,
            storage_service=storage_service
        )
        
        # 6. Create Controllers
        logger.debug("Creating IndexController")
        index_controller = IndexController(
            indexing_service=indexing_service,
            storage_service=storage_service
        )
        
        logger.debug("Creating SearchController")
        search_controller = SearchController(
            search_service=search_service
        )
        
        logger.info("ServiceFactory: All services created successfully")
        
        return index_controller, search_controller
