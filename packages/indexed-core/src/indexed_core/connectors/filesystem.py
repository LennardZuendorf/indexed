"""FileSystem connector for reading local files."""
import fnmatch
from pathlib import Path
from typing import Iterator, List
import logging

from indexed_core.models.document import Document

logger = logging.getLogger(__name__)


class FileSystemConnector:
    """Reads documents from filesystem.
    
    This connector discovers and reads files from local filesystem paths,
    applying include/exclude patterns for filtering.
    """
    
    def __init__(
        self,
        include_patterns: List[str],
        exclude_patterns: List[str]
    ):
        """Initialize filesystem connector.
        
        Args:
            include_patterns: Glob patterns for files to include (e.g., ["*.py", "*.md"]).
            exclude_patterns: Glob patterns for files to exclude (e.g., ["*.pyc", "__pycache__"]).
        """
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        logger.info(f"FileSystemConnector initialized with {len(include_patterns)} include and {len(exclude_patterns)} exclude patterns")
    
    def discover_documents(self, source: str) -> Iterator[Path]:
        """Discover documents from a filesystem path.
        
        Args:
            source: File or directory path.
            
        Yields:
            Path objects for discovered documents.
        """
        source_path = Path(source).resolve()
        
        if not source_path.exists():
            logger.error(f"Source path does not exist: {source_path}")
            return
        
        if source_path.is_file():
            if self._should_include(source_path):
                logger.debug(f"Yielding single file: {source_path}")
                yield source_path
            else:
                logger.debug(f"Skipping file (doesn't match patterns): {source_path}")
            return
        
        # Recursively walk directory
        logger.info(f"Discovering documents in directory: {source_path}")
        count = 0
        for path in source_path.rglob("*"):
            if path.is_file() and self._should_include(path):
                count += 1
                yield path
        
        logger.info(f"Discovered {count} documents in {source_path}")
    
    def read_document(self, path: Path) -> Document:
        """Read file content and create Document.
        
        Args:
            path: Path to file.
            
        Returns:
            Document object with content and metadata.
            
        Raises:
            IOError: If file cannot be read.
        """
        try:
            # Try UTF-8 first (most common)
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # Fallback to latin-1 (handles binary as text)
            logger.warning(f"Failed to read {path} as UTF-8, trying latin-1")
            try:
                content = path.read_text(encoding='latin-1')
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
                raise IOError(f"Cannot read file {path}: {e}")
        except Exception as e:
            logger.error(f"Error reading {path}: {e}")
            raise IOError(f"Cannot read file {path}: {e}")
        
        return Document.from_file(path, content)
    
    def supports_path(self, path: Path) -> bool:
        """Check if this connector supports the given path.
        
        Args:
            path: Path to check.
            
        Returns:
            True if path is an existing file or directory, False otherwise.
        """
        return path.exists() and (path.is_file() or path.is_dir())
    
    def _should_include(self, path: Path) -> bool:
        """Check if file should be included based on patterns.
        
        Args:
            path: Path to check.
            
        Returns:
            True if file matches include patterns and not exclude patterns.
        """
        # Check exclude patterns first (more efficient)
        for pattern in self.exclude_patterns:
            # Check if pattern matches filename
            if fnmatch.fnmatch(path.name, pattern):
                return False
            # Check if pattern matches any part of the path
            if any(fnmatch.fnmatch(part, pattern) for part in path.parts):
                return False
        
        # Check include patterns
        for pattern in self.include_patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True
        
        return False
