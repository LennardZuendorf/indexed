"""Domain models for documents and search results."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import uuid


@dataclass
class Document:
    """Represents a source document.
    
    A document is the original unit of content from a source (file, web page, etc.)
    that will be chunked and indexed.
    """
    
    id: str
    content: str
    source_path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def from_file(cls, path: Path, content: str) -> "Document":
        """Create a document from a file.
        
        Args:
            path: Path to the file.
            content: Content of the file.
            
        Returns:
            Document instance with file metadata.
        """
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            source_path=path,
            metadata={
                "filename": path.name,
                "extension": path.suffix,
                "size": len(content),
                "modified": datetime.fromtimestamp(path.stat().st_mtime) if path.exists() else None,
            }
        )


@dataclass
class Chunk:
    """Represents a chunk of a document.
    
    Documents are split into chunks for more granular indexing and retrieval.
    Each chunk maintains a reference to its parent document.
    """
    
    id: str
    document_id: str
    content: str
    index: int  # Chunk index within document (0-based)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_document(cls, document: Document, content: str, index: int) -> "Chunk":
        """Create a chunk from a document.
        
        Args:
            document: Parent document.
            content: Content of this chunk.
            index: Index of this chunk within the document.
            
        Returns:
            Chunk instance with inherited metadata.
        """
        return cls(
            id=f"{document.id}_chunk_{index}",
            document_id=document.id,
            content=content,
            index=index,
            metadata={
                **document.metadata,
                "source_path": str(document.source_path),
                "chunk_index": index,
                "document_created_at": document.created_at.isoformat(),
            }
        )


@dataclass
class SearchResult:
    """Represents a search result.
    
    Contains the matched chunk, its similarity score, and optionally
    the full parent document for context.
    """
    
    chunk: Chunk
    score: float
    document: Optional[Document] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation of the search result.
        """
        return {
            "chunk_id": self.chunk.id,
            "content": self.chunk.content,
            "score": self.score,
            "metadata": self.chunk.metadata,
            "document_id": self.chunk.document_id,
        }
