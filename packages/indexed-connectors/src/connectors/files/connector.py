"""FileSystem connector for indexing local files.

This connector wraps the existing FilesDocumentReader and FilesDocumentConverter
to provide a standardized BaseConnector interface.
"""

from typing import List
from .files_document_reader import FilesDocumentReader
from .files_document_converter import FilesDocumentConverter


class FileSystemConnector:
    """Connector for local file system documents.

    Discovers and indexes files from a local directory, supporting various
    file formats including markdown, text, PDF, DOCX, and more through the
    Unstructured library.

    Attributes:
        reader: FilesDocumentReader instance for discovering and reading files
        converter: FilesDocumentConverter instance for format conversion

    Examples:
        >>> # Basic usage
        >>> connector = FileSystemConnector(path="./docs")
        >>> index.add_collection("docs", connector)
        >>>
        >>> # With patterns
        >>> connector = FileSystemConnector(
        ...     path="./docs",
        ...     include_patterns=["*.md", "*.txt"],
        ...     exclude_patterns=["node_modules/*"]
        ... )
        >>> index.add_collection("docs", connector)
    """

    def __init__(
        self,
        path: str,
        include_patterns: List[str] = None,
        exclude_patterns: List[str] = None,
        fail_fast: bool = False,
    ):
        """Initialize FileSystem connector.

        Args:
            path: Root directory path to scan for files
            include_patterns: List of regex patterns for files to include.
                            Defaults to [".*"] (all files)
            exclude_patterns: List of regex patterns for files to exclude.
                            Defaults to []
            fail_fast: If True, stop on first file read error.
                      If False, skip errors and continue (default)

        Examples:
            >>> # Index all markdown files
            >>> connector = FileSystemConnector(
            ...     path="./docs",
            ...     include_patterns=[".*\\.md$"]
            ... )
            >>>
            >>> # Index code files, excluding tests
            >>> connector = FileSystemConnector(
            ...     path="./src",
            ...     include_patterns=[".*\\.(py|js|ts)$"],
            ...     exclude_patterns=[".*test.*", ".*/tests/.*"]
            ... )
        """
        self._path = path
        self._include_patterns = include_patterns or [".*"]
        self._exclude_patterns = exclude_patterns or []
        self._fail_fast = fail_fast

        # Initialize reader and converter
        self._reader = FilesDocumentReader(
            base_path=path,
            include_patterns=self._include_patterns,
            exclude_patterns=self._exclude_patterns,
            fail_fast=self._fail_fast,
        )
        self._converter = FilesDocumentConverter()

    @property
    def reader(self) -> FilesDocumentReader:
        """Return the document reader instance."""
        return self._reader

    @property
    def converter(self) -> FilesDocumentConverter:
        """Return the document converter instance."""
        return self._converter

    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "localFiles"

    def __repr__(self) -> str:
        """String representation of connector."""
        return (
            f"FileSystemConnector(path='{self._path}', "
            f"include_patterns={self._include_patterns}, "
            f"exclude_patterns={self._exclude_patterns})"
        )


__all__ = ["FileSystemConnector"]
