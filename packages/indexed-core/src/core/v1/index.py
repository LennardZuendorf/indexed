"""Main Index class for managing document collections."""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from .connectors import BaseConnector
from .engine.services import update, search, status, clear, SourceConfig
from .engine.factories.create_collection_factory import create_collection_creator

# Default indexer name (FAISS IndexFlatL2 with all-MiniLM-L6-v2 embeddings)
DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


@dataclass
class IndexConfig:
    """Simple configuration for the Index class.
    
    Attributes:
        default_indexer: Name of the default FAISS indexer configuration.
    """
    default_indexer: str = DEFAULT_INDEXER


class Index:
    """Main interface for indexed document search.

    Provides a simple, intuitive API for managing document collections
    and performing semantic search across them. Wraps the underlying
    service layer with a clean, user-friendly interface.

    Examples:
        >>> # Create index and add collections
        >>> index = Index()
        >>> index.add_collection("docs", connector="filesystem", path="./docs")
        >>> index.add_collection("jira", connector="jira", url="...", query="...")
        >>>
        >>> # Search across all collections
        >>> results = index.search("authentication methods")
        >>>
        >>> # Search specific collection
        >>> results = index.search("bug reports", collection="jira")
        >>>
        >>> # Update and maintain collections
        >>> index.update("docs")
        >>> status = index.status()
        >>> index.remove("old-collection")
    """

    def __init__(self, config: Optional[IndexConfig] = None):
        """Initialize index with optional configuration.

        Args:
            config: IndexConfig instance. If None, uses default configuration.

        Examples:
            >>> index = Index()  # Use defaults
            >>> config = IndexConfig(default_indexer="custom_indexer")
            >>> index = Index(config=config)  # Use custom config
        """
        self.config = config or IndexConfig()
        self._collections: Dict[str, SourceConfig] = {}

    def add_collection(self, name: str, connector: BaseConnector) -> None:
        """Add a new collection to the index.

        Creates a new document collection from the provided connector
        and indexes all documents for search.

        Args:
            name: Unique name for the collection
            connector: Connector instance implementing BaseConnector protocol.
                      Can be FileSystemConnector, JiraConnector, ConfluenceConnector, etc.

        Raises:
            TypeError: If connector doesn't implement BaseConnector protocol

        Examples:
            >>> from core.v1 import Index
            >>> from connectors import FileSystemConnector, JiraConnector
            >>>
            >>> index = Index()
            >>>
            >>> # Add filesystem collection
            >>> files = FileSystemConnector(path="./docs")
            >>> index.add_collection("docs", files)
            >>>
            >>> # Add Jira collection
            >>> jira = JiraConnector(
            ...     url="https://jira.example.com",
            ...     query="project = PROJ",
            ...     token="your-token"
            ... )
            >>> index.add_collection("jira-issues", jira)
        """
        # Verify connector implements BaseConnector protocol
        if not isinstance(connector, BaseConnector):
            raise TypeError(
                f"Connector must implement BaseConnector protocol. "
                f"Got {type(connector).__name__} instead."
            )

        # Create collection using connector's reader and converter
        creator = create_collection_creator(
            collection_name=name,
            indexers=[self.config.default_indexer],
            document_reader=connector.reader,
            document_converter=connector.converter,
            use_cache=True,
        )
        creator.run()

        # Track connector locally
        self._collections[name] = connector

    def search(
        self, query: str, collection: Optional[str] = None, max_results: int = 10
    ) -> Dict[str, Any]:
        """Search across collections using semantic similarity.

        Performs vector similarity search across all collections or
        a specific collection if specified.

        Args:
            query: Search query text
            collection: Optional specific collection name to search
            max_results: Maximum number of results to return (default: 10)

        Returns:
            Dictionary with collection names as keys and search results
            as values. Each result contains documents, scores, and metadata.

        Examples:
            >>> index = Index()
            >>> # Search all collections
            >>> results = index.search("How to configure authentication?")
            >>>
            >>> # Search specific collection
            >>> results = index.search("bug in login", collection="jira", max_results=5)
        """
        configs = None
        if collection:
            # Search specific collection - need to create a SourceConfig for it
            # Get the collection's indexer from status
            statuses = status([collection])
            if statuses:
                coll_status = statuses[0]
                configs = [
                    SourceConfig(
                        name=collection,
                        type="localFiles",  # Type doesn't matter for search
                        base_url_or_path="",  # Not used for search
                        indexer=coll_status.indexers[0],
                    )
                ]
        # If configs is None, search will auto-discover all collections

        return search(
            query, configs=configs, max_docs=max_results, max_chunks=max_results * 3
        )

    def update(self, collection: Optional[str] = None) -> None:
        """Update collections with new or modified documents.

        Re-indexes new and updated documents while preserving
        existing indexed content. For collections not tracked by this Index
        instance (e.g., created via CLI), uses the manifest to determine
        how to update.

        Args:
            collection: Specific collection name or None to update all

        Examples:
            >>> index = Index()
            >>> # Update specific collection
            >>> index.update("docs")
            >>>
            >>> # Update all collections
            >>> index.update()
        """
        from .engine.factories.update_collection_factory import create_collection_updater
        
        if collection:
            if collection in self._collections:
                # For tracked collections, create SourceConfig from connector
                connector = self._collections[collection]
                cfg = SourceConfig(
                    name=collection,
                    type=connector.connector_type,
                    base_url_or_path="",  # Not needed for update
                    indexer=self.config.default_indexer,
                )
                update([cfg])
            else:
                # Collection exists but not tracked - use update factory 
                # which reads configuration from manifest
                statuses = status([collection])
                if statuses:
                    updater = create_collection_updater(collection)
                    updater.run()
        else:
            # Update all tracked collections
            if self._collections:
                cfgs = [
                    SourceConfig(
                        name=name,
                        type=self._collections[name].connector_type,
                        base_url_or_path="",
                        indexer=self.config.default_indexer,
                    )
                    for name in self._collections
                ]
                update(cfgs)
            
            # Also update any discovered collections not tracked
            statuses = status()
            for s in statuses:
                if s.name not in self._collections:
                    updater = create_collection_updater(s.name)
                    updater.run()

    def status(self, collection: Optional[str] = None):
        """Get status information for collections.

        Returns metadata about collections including document count,
        chunk count, last update time, and storage information.

        Args:
            collection: Specific collection name or None for all

        Returns:
            Single CollectionStatus for specific collection, or
            List[CollectionStatus] for all collections

        Examples:
            >>> index = Index()
            >>> # Get status of all collections
            >>> all_status = index.status()
            >>>
            >>> # Get status of specific collection
            >>> docs_status = index.status("docs")
            >>> print(f"Documents: {docs_status.number_of_documents}")
        """
        if collection:
            result = status([collection])
            return result[0] if result else None
        else:
            return status()

    def remove(self, collection: str) -> None:
        """Remove a collection and its indexed data.

        Permanently deletes the collection and all its indexed documents
        from storage.

        Args:
            collection: Name of collection to remove

        Examples:
            >>> index = Index()
            >>> index.remove("old-docs")
        """
        clear([collection])
        if collection in self._collections:
            del self._collections[collection]

    def list_collections(self) -> List[str]:
        """List names of all tracked collections.

        Returns:
            List of collection names

        Examples:
            >>> index = Index()
            >>> collections = index.list_collections()
            >>> print(f"Collections: {', '.join(collections)}")
        """
        return list(self._collections.keys())
