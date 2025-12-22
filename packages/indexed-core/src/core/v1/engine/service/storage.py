"""Vector storage service using FAISS."""

import faiss
import numpy as np
import pickle
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from loguru import logger


class StorageService:
    """Manages vector storage with FAISS.

    This service wraps FAISS operations and provides a clean interface
    for adding, searching, and persisting vector embeddings.
    """

    def __init__(
        self,
        dimension: int,
        index_type: str = "IndexFlatL2",
        persistence_path: Optional[Path] = None,
    ):
        """Initialize storage service.

        Args:
            dimension: Embedding dimension.
            index_type: FAISS index type (IndexFlatL2, IndexFlatIP, etc.).
            persistence_path: Path to save/load index.
        """
        self.dimension = dimension
        self.index_type = index_type
        self.persistence_path = persistence_path
        self.index = self._create_index(index_type)
        self.id_mapping: Dict[int, str] = {}  # FAISS index -> chunk ID
        self.reverse_mapping: Dict[str, int] = {}  # chunk ID -> FAISS index
        self.chunk_metadata: Dict[str, Dict[str, Any]] = {}  # Store chunk metadata
        self.next_id = 0

        # Try to load existing index
        if persistence_path and persistence_path.exists():
            self.load()
            logger.info(f"Loaded existing index with {self.index.ntotal} vectors")

    def _create_index(self, index_type: str) -> faiss.Index:
        """Create FAISS index.

        Args:
            index_type: Type of FAISS index to create.

        Returns:
            FAISS index instance.
        """
        if index_type == "IndexFlatL2":
            return faiss.IndexFlatL2(self.dimension)
        elif index_type == "IndexFlatIP":
            return faiss.IndexFlatIP(self.dimension)
        else:
            raise ValueError(f"Unsupported index type: {index_type}")

    def add_vectors(
        self,
        vectors: np.ndarray,
        ids: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Add vectors to index.

        Args:
            vectors: Array of shape (n, dimension).
            ids: List of chunk IDs corresponding to vectors.
            metadata: Optional list of metadata dicts for each vector.
        """
        if vectors.shape[0] != len(ids):
            raise ValueError("Number of vectors must match number of IDs")

        if metadata and len(metadata) != len(ids):
            raise ValueError("Number of metadata entries must match number of IDs")

        # Ensure vectors are float32
        vectors = vectors.astype(np.float32)

        # Add to FAISS
        self.index.add(vectors)

        # Update mappings
        for i, chunk_id in enumerate(ids):
            faiss_idx = self.next_id + i
            self.id_mapping[faiss_idx] = chunk_id
            self.reverse_mapping[chunk_id] = faiss_idx

            # Store metadata if provided
            if metadata:
                self.chunk_metadata[chunk_id] = metadata[i]

        self.next_id += len(ids)
        logger.info(f"Added {len(ids)} vectors to index. Total: {self.index.ntotal}")

    def search(
        self, query_vector: np.ndarray, top_k: int = 10
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Search for similar vectors.

        Args:
            query_vector: Query vector of shape (dimension,).
            top_k: Number of results to return.

        Returns:
            List of (chunk_id, similarity_score, metadata) tuples.
        """
        if self.index.ntotal == 0:
            logger.warning("Index is empty, returning no results")
            return []

        # Ensure query is 2D and float32
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        query_vector = query_vector.astype(np.float32)

        # Search
        distances, indices = self.index.search(
            query_vector, min(top_k, self.index.ntotal)
        )

        # Map back to chunk IDs with metadata
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:  # No result
                continue
            chunk_id = self.id_mapping.get(int(idx))
            if chunk_id:
                # Convert L2 distance to similarity score (inverse)
                score = 1.0 / (1.0 + float(dist))
                metadata = self.chunk_metadata.get(chunk_id, {})
                results.append((chunk_id, score, metadata))

        return results

    def delete_by_ids(self, ids: List[str]) -> None:
        """Remove vectors by chunk IDs.

        Note: FAISS doesn't support efficient deletion. This currently just
        removes from mappings but not the index itself. For full removal,
        index rebuild would be required.

        Args:
            ids: List of chunk IDs to remove.
        """
        removed_count = 0
        for chunk_id in ids:
            if chunk_id in self.reverse_mapping:
                faiss_idx = self.reverse_mapping[chunk_id]
                del self.id_mapping[faiss_idx]
                del self.reverse_mapping[chunk_id]
                if chunk_id in self.chunk_metadata:
                    del self.chunk_metadata[chunk_id]
                removed_count += 1

        if removed_count > 0:
            logger.warning(
                f"Removed {removed_count} mappings. "
                "Note: FAISS vectors not actually deleted - consider rebuilding index"
            )

    def save(self) -> None:
        """Persist index and mappings to disk."""
        if not self.persistence_path:
            logger.warning("No persistence path set, skipping save")
            return

        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        faiss.write_index(self.index, str(self.persistence_path))

        # Save mappings and metadata
        mapping_path = self.persistence_path.with_suffix(".mappings.pkl")
        with open(mapping_path, "wb") as f:
            pickle.dump(
                {
                    "id_mapping": self.id_mapping,
                    "reverse_mapping": self.reverse_mapping,
                    "chunk_metadata": self.chunk_metadata,
                    "next_id": self.next_id,
                },
                f,
            )

        logger.info(f"Saved index to {self.persistence_path}")

    def load(self) -> None:
        """Load index and mappings from disk."""
        if not self.persistence_path or not self.persistence_path.exists():
            logger.warning("No index file found, starting fresh")
            return

        # Load FAISS index
        self.index = faiss.read_index(str(self.persistence_path))

        # Load mappings and metadata
        mapping_path = self.persistence_path.with_suffix(".mappings.pkl")
        if mapping_path.exists():
            with open(mapping_path, "rb") as f:
                data = pickle.load(f)
                self.id_mapping = data["id_mapping"]
                self.reverse_mapping = data["reverse_mapping"]
                self.chunk_metadata = data.get("chunk_metadata", {})
                self.next_id = data["next_id"]

        logger.info(
            f"Loaded index from {self.persistence_path}. Total vectors: {self.index.ntotal}"
        )

    def clear(self) -> None:
        """Clear all vectors and mappings."""
        self.index = self._create_index(self.index_type)
        self.id_mapping = {}
        self.reverse_mapping = {}
        self.chunk_metadata = {}
        self.next_id = 0
        logger.info("Cleared index")

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics.

        Returns:
            Dictionary of index statistics.
        """
        return {
            "total_vectors": self.index.ntotal,
            "dimension": self.dimension,
            "index_type": self.index_type,
            "is_trained": self.index.is_trained,
            "unique_chunks": len(self.reverse_mapping),
        }
