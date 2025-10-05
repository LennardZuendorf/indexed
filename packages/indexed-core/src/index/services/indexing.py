"""Indexing service for document ingestion pipeline."""
from typing import List, Dict, Any
from pathlib import Path
import logging

from index.models.document import Document, Chunk
from index.services.embedding import EmbeddingService
from index.services.storage import StorageService
from index.connectors.base import DocumentConnector

logger = logging.getLogger(__name__)


class IndexingService:
    """Orchestrates document indexing pipeline.
    
    This service coordinates the flow from raw documents through
    chunking, embedding generation, and storage.
    """
    
    def __init__(
        self,
        connectors: List[DocumentConnector],
        embedding_service: EmbeddingService,
        storage_service: StorageService,
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ):
        """Initialize indexing service.
        
        Args:
            connectors: List of document connectors to use.
            embedding_service: Service for generating embeddings.
            storage_service: Service for storing vectors.
            chunk_size: Maximum size of each chunk in characters.
            chunk_overlap: Number of characters to overlap between chunks.
        """
        self.connectors = connectors
        self.embedding_service = embedding_service
        self.storage_service = storage_service
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.info(
            f"IndexingService initialized with {len(connectors)} connectors, "
            f"chunk_size={chunk_size}, overlap={chunk_overlap}"
        )
    
    def index_source(self, source: str) -> Dict[str, Any]:
        """Index documents from a source.
        
        Args:
            source: Source path or identifier.
            
        Returns:
            Statistics about the indexing operation.
        """
        logger.info(f"Starting indexing from source: {source}")
        
        # Find appropriate connector
        connector = self._get_connector(source)
        if not connector:
            raise ValueError(f"No connector found that supports source: {source}")
        
        documents_processed = 0
        chunks_created = 0
        chunks_indexed = 0
        
        # Process documents in batches for efficiency
        batch_chunks = []
        batch_size = 50  # Process 50 chunks at a time
        
        for doc_path in connector.discover_documents(source):
            try:
                # Read document
                document = connector.read_document(doc_path)
                documents_processed += 1
                logger.debug(f"Processing document: {doc_path}")
                
                # Chunk document
                chunks = self._chunk_document(document)
                chunks_created += len(chunks)
                
                # Add to batch
                batch_chunks.extend(chunks)
                
                # Process batch when it reaches size
                if len(batch_chunks) >= batch_size:
                    indexed = self._index_chunks(batch_chunks)
                    chunks_indexed += indexed
                    batch_chunks = []
                    
            except Exception as e:
                logger.error(f"Error processing {doc_path}: {e}")
                continue
        
        # Process remaining chunks
        if batch_chunks:
            indexed = self._index_chunks(batch_chunks)
            chunks_indexed += indexed
        
        # Save index
        self.storage_service.save()
        
        stats = {
            "documents_processed": documents_processed,
            "chunks_created": chunks_created,
            "chunks_indexed": chunks_indexed,
            "source": source,
        }
        
        logger.info(
            f"Indexing complete: {documents_processed} documents, "
            f"{chunks_indexed} chunks indexed"
        )
        
        return stats
    
    def _get_connector(self, source: str) -> DocumentConnector:
        """Find a connector that supports the given source.
        
        Args:
            source: Source path or identifier.
            
        Returns:
            Compatible connector or None.
        """
        source_path = Path(source)
        for connector in self.connectors:
            if connector.supports_path(source_path):
                return connector
        return None
    
    def _chunk_document(self, document: Document) -> List[Chunk]:
        """Split document into chunks.
        
        Args:
            document: Document to chunk.
            
        Returns:
            List of chunks.
        """
        content = document.content
        chunks = []
        
        # Simple character-based chunking with overlap
        # For production, consider using more sophisticated methods like
        # sentence-aware chunking or semantic chunking
        
        if len(content) <= self.chunk_size:
            # Document fits in one chunk
            chunks.append(Chunk.from_document(document, content, 0))
        else:
            # Split into overlapping chunks
            start = 0
            index = 0
            
            while start < len(content):
                end = start + self.chunk_size
                chunk_content = content[start:end]
                
                # Try to break at word boundary if possible
                if end < len(content) and not content[end].isspace():
                    # Find last space in chunk
                    last_space = chunk_content.rfind(' ')
                    if last_space > self.chunk_size // 2:  # Only if space is not too early
                        chunk_content = chunk_content[:last_space]
                        end = start + last_space
                
                chunks.append(Chunk.from_document(document, chunk_content.strip(), index))
                index += 1
                
                # Move start with overlap
                start = end - self.chunk_overlap
                
                # Avoid infinite loop on edge cases
                if start <= end - self.chunk_size:
                    start = end
        
        logger.debug(f"Chunked document {document.id} into {len(chunks)} chunks")
        return chunks
    
    def _index_chunks(self, chunks: List[Chunk]) -> int:
        """Index a batch of chunks.
        
        Args:
            chunks: List of chunks to index.
            
        Returns:
            Number of chunks successfully indexed.
        """
        if not chunks:
            return 0
        
        try:
            # Extract content and IDs
            texts = [chunk.content for chunk in chunks]
            chunk_ids = [chunk.id for chunk in chunks]
            # Include content in metadata for retrieval
            metadata = [{**chunk.metadata, 'content': chunk.content} for chunk in chunks]
            
            # Generate embeddings
            logger.debug(f"Generating embeddings for {len(texts)} chunks")
            embeddings = self.embedding_service.embed_batch(texts, show_progress=False)
            
            # Store vectors
            logger.debug(f"Storing {len(embeddings)} vectors")
            self.storage_service.add_vectors(embeddings, chunk_ids, metadata)
            
            return len(chunks)
            
        except Exception as e:
            logger.error(f"Error indexing chunk batch: {e}")
            return 0
