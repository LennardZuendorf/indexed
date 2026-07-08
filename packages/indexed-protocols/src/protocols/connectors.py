"""Base connector protocol for document sources.

This module defines the standard interface that all connectors must implement.
Connectors encapsulate the logic for discovering, reading, and converting
documents from various sources (Jira, Confluence, local files, etc.).
"""

from typing import (
    Any,
    ClassVar,
    Dict,
    Iterator,
    List,
    Protocol,
    Union,
    runtime_checkable,
)

from protocols.models import ConvertedDocument


@runtime_checkable
class DocumentReader(Protocol):
    """Protocol for fetching raw documents from a source.

    Declares exactly what the engine calls on a reader
    (``documents_collection_creator``): the document count, the document
    iterator, and the reader-details block persisted to the manifest. A reader
    missing one of these is a mypy error, not a runtime ``AttributeError``.
    """

    def get_number_of_documents(self) -> int:
        """Return the number of documents the reader will yield."""
        ...

    def read_all_documents(self) -> Iterator[Any]:
        """Yield the raw documents from the source."""
        ...

    def get_reader_details(self) -> Dict[str, Any]:
        """Return the per-source ``reader`` block for the manifest (has ``type``)."""
        ...


@runtime_checkable
class DocumentConverter(Protocol):
    """Protocol for converting raw documents into searchable chunks."""

    def convert(
        self, doc: Any
    ) -> Union[Iterator[ConvertedDocument], List[Dict[str, Any]]]:
        """Convert a raw document into the v1 converted-document form."""
        ...


@runtime_checkable
class BaseConnector(Protocol):
    """Protocol defining the standard interface for document connectors.

    All connectors must implement this protocol to be usable with the Index class.
    Connectors are responsible for:
    - Discovering available documents (loader)
    - Reading document content (reader)
    - Converting to standard format (converter)

    The core package only knows about this protocol, not specific implementations,
    enabling a true plugin architecture where new connectors can be added without
    modifying core code.

    Attributes:
        reader: Document reader instance that handles fetching documents
        converter: Document converter instance that handles format conversion

    Examples:
        >>> class MyConnector:
        ...     def __init__(self, **config):
        ...         self.reader = MyReader(config)
        ...         self.converter = MyConverter()
        ...
        ...     @property
        ...     def connector_type(self):
        ...         return "my-source"
        >>>
        >>> connector = MyConnector(url="...")
        >>> index.add_collection("mycollection", connector)
    """

    # Optional metadata object (not required by protocol, but commonly present)
    META: ClassVar[Any]

    @property
    def reader(self):
        """Document reader instance.

        The reader handles discovering and fetching raw documents from the source.
        Must implement methods like get_number_of_documents() and read_all_documents().

        Returns:
            Reader instance compatible with DocumentCollectionCreator
        """
        ...

    @property
    def converter(self):
        """Document converter instance.

        The converter transforms raw documents from the source into the standard
        indexed format with chunks and metadata.

        Returns:
            Converter instance compatible with DocumentCollectionCreator
        """
        ...

    @property
    def connector_type(self) -> str:
        """Return the connector type identifier.

        This string identifies the connector type for storage and logging purposes.
        Should be a unique, lowercase identifier (e.g., 'jira', 'confluence', 'files').

        Returns:
            str: Connector type identifier

        Examples:
            >>> connector.connector_type
            'jira'
        """
        ...

    # --- Configuration integration (optional but recommended) ---
    @classmethod
    def config_spec(cls) -> Dict[str, Dict[str, Any]]:
        """Return a specification of required/optional config values.

        The spec is a mapping of field name -> metadata dict with keys:
          - type: str  (e.g., 'str', 'int', 'bool', 'list')
          - required: bool
          - secret: bool  (True for values that must come from env/.env)
          - default: Any (optional)
          - description: str (optional)
        """
        ...

    @classmethod
    def from_config(cls, config_service: Any) -> "BaseConnector":
        """Create a connector instance from a ConfigService.

        Args:
            config_service: ConfigService instance (indexed_config.ConfigService)
        """
        ...


__all__ = ["BaseConnector", "DocumentConverter", "DocumentReader"]
