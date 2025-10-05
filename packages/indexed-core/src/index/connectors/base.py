"""Base connector protocol for document sources."""
from typing import Protocol, Iterator
from pathlib import Path


class DocumentConnector(Protocol):
    """Protocol for document connectors.
    
    Document connectors are responsible for discovering and reading documents
    from various sources (filesystem, git, APIs, etc.).
    """
    
    def discover_documents(self, source: str) -> Iterator[Path]:
        """Discover documents from a source.
        
        Args:
            source: Source path or identifier (e.g., file path, URL, repo URL).
            
        Yields:
            Path objects for discovered documents.
        """
        ...
    
    def read_document(self, path: Path) -> "Document":
        """Read and parse a document.
        
        Args:
            path: Path to document.
            
        Returns:
            Document object with content and metadata.
        """
        ...
    
    def supports_path(self, path: Path) -> bool:
        """Check if this connector supports the given path.
        
        Args:
            path: Path to check.
            
        Returns:
            True if this connector can handle the path, False otherwise.
        """
        ...
