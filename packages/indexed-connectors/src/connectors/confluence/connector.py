"""Confluence connector for indexing Confluence pages.

This connector wraps the existing ConfluenceDocumentReader and ConfluenceDocumentConverter
to provide a standardized BaseConnector interface for both Confluence Server/Data Center
and Confluence Cloud.
"""

from typing import Optional
from .confluence_document_reader import ConfluenceDocumentReader
from .confluence_document_converter import ConfluenceDocumentConverter
from .confluence_cloud_document_reader import ConfluenceCloudDocumentReader
from .confluence_cloud_document_converter import ConfluenceCloudDocumentConverter


class ConfluenceConnector:
    """Connector for Confluence Server/Data Center pages.
    
    Discovers and indexes Confluence pages based on CQL queries. Supports both
    token-based and username/password authentication. Can optionally include
    page comments.
    
    Attributes:
        reader: ConfluenceDocumentReader instance for API calls
        converter: ConfluenceDocumentConverter instance for format conversion
    
    Examples:
        >>> # Token authentication (recommended)
        >>> connector = ConfluenceConnector(
        ...     url="https://confluence.example.com",
        ...     query="space = DEV",
        ...     token="your-token"
        ... )
        >>> index.add_collection("confluence-pages", connector)
        >>> 
        >>> # Include only top-level comments
        >>> connector = ConfluenceConnector(
        ...     url="https://confluence.example.com",
        ...     query="type = page",
        ...     token="your-token",
        ...     read_all_comments=False
        ... )
    """
    
    def __init__(
        self,
        url: str,
        query: str,
        token: Optional[str] = None,
        login: Optional[str] = None,
        password: Optional[str] = None,
        read_all_comments: bool = True
    ):
        """Initialize Confluence Server/Data Center connector.
        
        Args:
            url: Confluence base URL (e.g., https://confluence.example.com)
            query: CQL query to filter pages
            token: Bearer token for authentication (recommended)
            login: Username for basic auth (if token not provided)
            password: Password for basic auth (if token not provided)
            read_all_comments: If True, read all comments. If False, only
                              read top-level comments (default: True)
            
        Raises:
            ValueError: If neither token nor login/password are provided
            
        Examples:
            >>> connector = ConfluenceConnector(
            ...     url="https://confluence.example.com",
            ...     query="space = MYSPACE AND type = page",
            ...     token="bearer-token-here"
            ... )
        """
        if not token and (not login or not password):
            raise ValueError(
                "Either 'token' or both 'login' and 'password' must be provided"
            )
        
        self._url = url
        self._query = query
        self._read_all_comments = read_all_comments
        
        # Initialize reader and converter
        self._reader = ConfluenceDocumentReader(
            base_url=url,
            query=query,
            token=token,
            login=login,
            password=password,
            read_all_comments=read_all_comments
        )
        self._converter = ConfluenceDocumentConverter()
    
    @property
    def reader(self) -> ConfluenceDocumentReader:
        """Return the document reader instance."""
        return self._reader
    
    @property
    def converter(self) -> ConfluenceDocumentConverter:
        """Return the document converter instance."""
        return self._converter
    
    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "confluence"
    
    def __repr__(self) -> str:
        """String representation of connector."""
        return f"ConfluenceConnector(url='{self._url}', query='{self._query}')"


class ConfluenceCloudConnector:
    """Connector for Confluence Cloud pages.
    
    Discovers and indexes Confluence Cloud pages using Atlassian Cloud API.
    Requires email and API token for authentication.
    
    Attributes:
        reader: ConfluenceCloudDocumentReader instance for API calls
        converter: ConfluenceCloudDocumentConverter instance for format conversion
    
    Examples:
        >>> connector = ConfluenceCloudConnector(
        ...     url="https://company.atlassian.net/wiki",
        ...     query="space = DEV",
        ...     email="user@example.com",
        ...     api_token="your-api-token"
        ... )
        >>> index.add_collection("confluence-cloud", connector)
    """
    
    def __init__(
        self,
        url: str,
        query: str,
        email: str,
        api_token: str,
        read_all_comments: bool = True
    ):
        """Initialize Confluence Cloud connector.
        
        Args:
            url: Confluence Cloud URL (e.g., https://company.atlassian.net/wiki)
            query: CQL query to filter pages
            email: Atlassian account email
            api_token: Atlassian API token (generate at 
                      https://id.atlassian.com/manage/api-tokens)
            read_all_comments: If True, read all comments. If False, only
                              read top-level comments (default: True)
                      
        Examples:
            >>> connector = ConfluenceCloudConnector(
            ...     url="https://mycompany.atlassian.net/wiki",
            ...     query="space = DOCS",
            ...     email="me@example.com",
            ...     api_token="ATATT..."
            ... )
        """
        self._url = url
        self._query = query
        self._read_all_comments = read_all_comments
        
        # Initialize reader and converter
        self._reader = ConfluenceCloudDocumentReader(
            base_url=url,
            query=query,
            email=email,
            api_token=api_token,
            read_all_comments=read_all_comments
        )
        self._converter = ConfluenceCloudDocumentConverter()
    
    @property
    def reader(self) -> ConfluenceCloudDocumentReader:
        """Return the document reader instance."""
        return self._reader
    
    @property
    def converter(self) -> ConfluenceCloudDocumentConverter:
        """Return the document converter instance."""
        return self._converter
    
    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "confluenceCloud"
    
    def __repr__(self) -> str:
        """String representation of connector."""
        return f"ConfluenceCloudConnector(url='{self._url}', query='{self._query}')"


__all__ = ["ConfluenceConnector", "ConfluenceCloudConnector"]
