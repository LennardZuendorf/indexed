"""FileSystem connector for indexing local files.

This connector wraps the existing FilesDocumentReader and FilesDocumentConverter
to provide a standardized BaseConnector interface.
"""

from typing import ClassVar, List
from core.v1.connectors.metadata import ConnectorMetadata
from .files_document_reader import FilesDocumentReader
from .files_document_converter import FilesDocumentConverter
from .schema import FileSystemConfig


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

    # Metadata for CLI generation and compatibility
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="files",
        display_name="Local Files",
        description="Index documents from local filesystem",
        config_class=FileSystemConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create --type files --name docs",
    )

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
        # Validate and normalize configuration using Pydantic
        config = FileSystemConfig(
            path=path,
            include_patterns=include_patterns or [".*"],
            exclude_patterns=exclude_patterns or [],
            fail_fast=fail_fast,
        )

        self._path = config.path
        self._include_patterns = config.include_patterns
        self._exclude_patterns = config.exclude_patterns
        self._fail_fast = config.fail_fast

        # Initialize reader and converter
        self._reader = FilesDocumentReader(
            base_path=self._path,
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

    # --- Config integration ---
    @classmethod
    def config_spec(cls) -> dict:
        """Return specification of required/optional config values.

        Returns a mapping of field name -> metadata dict describing
        configuration parameters for config-driven instantiation.

        Returns:
            dict: Configuration specification with keys:
                - type: str (e.g., 'str', 'list', 'bool')
                - required: bool
                - secret: bool (always False for local files)
                - default: Any (optional)
                - description: str

        Examples:
            >>> spec = FileSystemConnector.config_spec()
            >>> spec['path']['required']
            True
            >>> spec['include_patterns']['type']
            'list'
        """
        return {
            "path": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Root directory path to scan for files",
            },
            "include_patterns": {
                "type": "list",
                "required": False,
                "secret": False,
                "default": [".*"],
                "description": "List of regex patterns for files to include",
            },
            "exclude_patterns": {
                "type": "list",
                "required": False,
                "secret": False,
                "default": [],
                "description": "List of regex patterns for files to exclude",
            },
            "fail_fast": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": False,
                "description": "Stop indexing on first error (True) or continue (False)",
            },
        }

    @classmethod
    def from_config(cls, config_service) -> "FileSystemConnector":
        """Create FileSystemConnector from ConfigService.

        Registers FileSystemConfig spec and extracts configuration values.

        Args:
            config_service: ConfigService instance with config loaded.

        Returns:
            Configured FileSystemConnector instance.

        Raises:
            ValueError: If required config values are missing or invalid.

        Examples:
            >>> from indexed_config import ConfigService
            >>> config = ConfigService()
            >>> connector = FileSystemConnector.from_config(config)
        """
        # Register our config spec
        config_service.register(FileSystemConfig, path="sources.files")

        # Bind and get our config
        provider = config_service.bind()
        cfg = provider.get(FileSystemConfig)

        # Create instance with config values
        return cls(
            path=cfg.path,
            include_patterns=cfg.include_patterns,
            exclude_patterns=cfg.exclude_patterns,
            fail_fast=cfg.fail_fast,
        )


__all__ = ["FileSystemConnector"]
