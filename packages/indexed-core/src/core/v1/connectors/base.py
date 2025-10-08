"""Base connector protocol for document sources.

This module defines the standard interface that all connectors must implement.
Connectors encapsulate the logic for discovering, reading, and converting
documents from various sources (Jira, Confluence, local files, etc.).

The core package only depends on this protocol, making connectors true plugins.
"""

from typing import Protocol, runtime_checkable


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


__all__ = ["BaseConnector"]
