"""Confluence connector for indexing Confluence pages.

This connector wraps the existing ConfluenceDocumentReader and ConfluenceDocumentConverter
to provide a standardized BaseConnector interface for both Confluence Server/Data Center
and Confluence Cloud.

Both connectors implement the BaseConnector protocol, exposing reader, converter, and
connector_type properties. They support both direct instantiation and configuration-driven
creation via config_spec() and from_config() class methods.

Comment depth handling:
- read_all_comments=True: Index all nested comments
- read_all_comments=False: Index only top-level comments
- Legacy readOnlyFirstLevelComments setting is automatically mapped to read_all_comments
"""

import os
from typing import ClassVar, Optional
from core.v1.connectors.metadata import ConnectorMetadata
from core.v1.config.settings import _get_env_var
from .confluence_document_reader import ConfluenceDocumentReader
from .confluence_document_converter import ConfluenceDocumentConverter
from .confluence_cloud_document_reader import ConfluenceCloudDocumentReader
from .confluence_cloud_document_converter import ConfluenceCloudDocumentConverter
from .schema import ConfluenceConfig, ConfluenceCloudConfig


def _safe_str_attr(obj, name: str, default: str) -> str:
    """Safely get string attribute, handling MagicMock in tests.
    
    Args:
        obj: Object to get attribute from
        name: Attribute name
        default: Default value if attribute missing or not a string
        
    Returns:
        String attribute value or default
    """
    val = getattr(obj, name, default)
    return val if isinstance(val, str) else default


class ConfluenceConnector:
    # Metadata for CLI generation and compatibility
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="confluence",
        display_name="Confluence (Server/Data Center)",
        description="Index Confluence pages using CQL queries",
        config_class=ConfluenceConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create --type confluence --name wiki",
    )
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
        read_all_comments: bool = True,
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
            read_all_comments=read_all_comments,
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

    # --- Configuration integration ---
    @classmethod
    def config_spec(cls) -> dict:
        return {
            "base_url": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Confluence base URL (Server/Data Center)",
            },
            "query": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Base CQL query",
            },
            # Auth alternatives (token OR login+password)
            "token_env": {
                "type": "str",
                "required": False,
                "secret": True,
                "default": "CONF_TOKEN",
                "description": "Env var name containing API token",
            },
            "login_env": {
                "type": "str",
                "required": False,
                "secret": True,
                "default": "CONF_LOGIN",
                "description": "Env var name for basic auth username",
            },
            "password_env": {
                "type": "str",
                "required": False,
                "secret": True,
                "default": "CONF_PASSWORD",
                "description": "Env var name for basic auth password",
            },
            "read_all_comments": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": True,
                "description": "Read nested comments (vs top-level only)",
            },
        }

    @classmethod
    def from_config(cls, config_service, namespace: str) -> "ConfluenceConnector":
        settings = config_service.get()
        # Navigate by dotted path via getattr
        section = settings
        for part in namespace.split("."):
            section = getattr(section, part)
        # Expect dict-like attributes: base_url, query
        base_url = getattr(section, "base_url", None)
        query = getattr(section, "cql", None) or getattr(section, "query", None)
        if not base_url or not query:
            raise ValueError("Confluence (Server/DC) config requires base_url and query")
        
        # Secrets via env - use safe getattr to handle MagicMock in tests
        token_env = _safe_str_attr(section, "token_env", "CONF_TOKEN")
        login_env = _safe_str_attr(section, "login_env", "CONF_LOGIN")
        password_env = _safe_str_attr(section, "password_env", "CONF_PASSWORD")
        
        token = os.getenv(token_env) or _get_env_var(token_env)
        login = os.getenv(login_env) or _get_env_var(login_env)
        password = os.getenv(password_env) or _get_env_var(password_env)
        
        if not token and (not login or not password):
            raise ValueError(
                "Either 'token' or both 'login' and 'password' must be provided"
            )
        
        # Handle read_all_comments with legacy compatibility
        read_all_comments = getattr(section, "read_all_comments", True)
        # Check legacy readOnlyFirstLevelComments (both camelCase and snake_case)
        if (getattr(section, "read_only_first_level_comments", None) is True or 
            getattr(section, "readOnlyFirstLevelComments", None) is True):
            read_all_comments = False
            
        return cls(
            url=base_url, 
            query=query, 
            token=token, 
            login=login, 
            password=password,
            read_all_comments=read_all_comments
        )


class ConfluenceCloudConnector:
    # Metadata for CLI generation and compatibility
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="confluenceCloud",
        display_name="Confluence Cloud",
        description="Index Confluence Cloud pages via Atlassian Cloud API",
        config_class=ConfluenceCloudConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create --type confluenceCloud --name wiki",
    )
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
        read_all_comments: bool = True,
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
            read_all_comments=read_all_comments,
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

    # --- Configuration integration ---
    @classmethod
    def config_spec(cls) -> dict:
        return {
            "base_url": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Confluence Cloud URL (e.g., https://company.atlassian.net/wiki)",
            },
            "query": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Base CQL query",
            },
            "email": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Atlassian account email",
            },
            "api_token_env": {
                "type": "str",
                "required": True,
                "secret": True,
                "default": "ATLASSIAN_TOKEN",
                "description": "Env var name containing Atlassian API token",
            },
            "read_all_comments": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": True,
                "description": "Read nested comments (vs top-level only)",
            },
        }

    @classmethod
    def from_config(cls, config_service, namespace: str) -> "ConfluenceCloudConnector":
        settings = config_service.get()
        section = settings
        for part in namespace.split("."):
            section = getattr(section, part)
        base_url = getattr(section, "base_url", None)
        email = getattr(section, "email", None) or os.getenv("ATLASSIAN_EMAIL") or _get_env_var("ATLASSIAN_EMAIL")
        query = getattr(section, "cql", None) or getattr(section, "query", None)
        if not base_url or not email or not query:
            raise ValueError("Confluence Cloud config requires base_url, email, and query (cql)")
        
        # Secrets resolution: prefer ATLASSIAN_TOKEN, fallback to configured api_token_env
        token_env_name = _safe_str_attr(section, "api_token_env", "ATLASSIAN_TOKEN")
        api_token = os.getenv("ATLASSIAN_TOKEN") or _get_env_var(token_env_name)
        if not api_token:
            raise ValueError(
                "Missing Atlassian API token. Set ATLASSIAN_TOKEN or the configured api_token_env."
            )
        
        # Handle read_all_comments with legacy compatibility
        read_all_comments = getattr(section, "read_all_comments", True)
        # Check legacy readOnlyFirstLevelComments (both camelCase and snake_case)
        if (getattr(section, "read_only_first_level_comments", None) is True or 
            getattr(section, "readOnlyFirstLevelComments", None) is True):
            read_all_comments = False
            
        return cls(
            url=base_url, 
            query=query, 
            email=email, 
            api_token=api_token,
            read_all_comments=read_all_comments
        )


__all__ = ["ConfluenceConnector", "ConfluenceCloudConnector"]
