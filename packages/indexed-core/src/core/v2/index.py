"""Index facade — the main user-facing API for v2.

Same API shape as v1 Index but powered by LlamaIndex internally.
All heavy imports are deferred to method bodies for fast CLI startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class IndexConfig:
    """Configuration for the v2 Index facade."""

    embed_model_name: str = "all-MiniLM-L6-v2"
    vector_store_type: str = "faiss"


class Index:
    """Main interface for indexed v2 document search.

    Provides a simple, intuitive API for managing document collections
    and performing semantic search. Wraps the v2 service layer.

    Examples::

        from core.v2 import Index

        index = Index()
        index.add_collection("docs", connector=files_connector)
        results = index.search("authentication methods")
    """

    def __init__(self, config: Optional[IndexConfig] = None) -> None:
        self.config = config or IndexConfig()
        self._collections: Dict[str, Any] = {}

    def add_collection(self, name: str, connector: Any) -> dict[str, Any]:
        """Create a new collection from a connector.

        Args:
            name: Unique collection name.
            connector: BaseConnector instance.

        Returns:
            Manifest dict with collection metadata.
        """
        from .services.collection_service import create

        result = create(
            name,
            connector,
            embed_model_name=self.config.embed_model_name,
            store_type=self.config.vector_store_type,
        )
        self._collections[name] = connector
        return result

    def search(
        self,
        query: str,
        collection: Optional[str] = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Search across collections using semantic similarity.

        Args:
            query: Search query text.
            collection: Optional specific collection name.
            max_results: Maximum documents to return.

        Returns:
            Dict with search results.
        """
        from .services.search_service import search as _search

        if collection:
            from .services.models import SourceConfig

            configs = [
                SourceConfig(
                    name=collection,
                    type="localFiles",
                    base_url_or_path="",
                )
            ]
            return _search(
                query,
                configs=configs,
                max_docs=max_results,
                embed_model_name=self.config.embed_model_name,
            )

        return _search(
            query,
            max_docs=max_results,
            embed_model_name=self.config.embed_model_name,
        )

    def update(self, collection: Optional[str] = None) -> None:
        """Update collections by re-indexing from their connectors.

        Args:
            collection: Specific collection name or None for all tracked.
        """
        from .errors import CollectionNotFoundError
        from .services.collection_service import update as _update

        if collection is not None:
            if collection not in self._collections:
                raise CollectionNotFoundError(collection)
            _update(
                collection,
                self._collections[collection],
                embed_model_name=self.config.embed_model_name,
                store_type=self.config.vector_store_type,
            )
            return

        for name, conn in self._collections.items():
            _update(
                name,
                conn,
                embed_model_name=self.config.embed_model_name,
                store_type=self.config.vector_store_type,
            )

    def status(self, collection: Optional[str] = None) -> Any:
        """Get status for collections.

        Args:
            collection: Specific collection or None for all.

        Returns:
            Single CollectionStatus or list of CollectionStatus.
        """
        from .services.inspect_service import status as _status

        if collection:
            result = _status([collection])
            return result[0] if result else None
        return _status()

    def remove(self, collection: str) -> None:
        """Remove a collection and its data from disk."""
        from .services.collection_service import clear

        clear([collection])
        self._collections.pop(collection, None)

    def list_collections(self) -> List[str]:
        """List names of all tracked collections."""
        return list(self._collections.keys())
