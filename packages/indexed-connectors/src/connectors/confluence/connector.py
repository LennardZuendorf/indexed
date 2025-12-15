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

from typing import ClassVar, Optional
from core.v1.connectors.metadata import ConnectorMetadata
from .confluence_document_reader import ConfluenceDocumentReader
from .confluence_document_converter import ConfluenceDocumentConverter
from .confluence_cloud_document_reader import ConfluenceCloudDocumentReader
from .confluence_cloud_document_converter import ConfluenceCloudDocumentConverter
from .schema import ConfluenceConfig, ConfluenceCloudConfig


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
    def from_config(cls, config_service) -> "ConfluenceConnector":
        """Create ConfluenceConnector from ConfigService.
        
        Registers ConfluenceConfig spec and extracts configuration values.
        
        Args:
            config_service: ConfigService instance with config loaded.
            
        Returns:
            Configured ConfluenceConnector instance.
            
        Raises:
            ValueError: If required config values are missing.
            
        Examples:
            >>> from indexed_config import ConfigService
            >>> config = ConfigService()
            >>> connector = ConfluenceConnector.from_config(config)
        """
        # Register our config spec
        config_service.register(ConfluenceConfig, path="sources.confluence.server")
        
        # Bind and get our config
        provider = config_service.bind()
        cfg = provider.get(ConfluenceConfig)
        
        # Create instance with config values
        return cls(
            url=cfg.url,
            query=cfg.query,
            token=cfg.get_token(),
            login=cfg.get_login(),
            password=cfg.get_password(),
            read_all_comments=cfg.read_all_comments,
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
    def from_config(cls, config_service) -> "ConfluenceCloudConnector":
        """Create ConfluenceCloudConnector from ConfigService.
        
        Registers ConfluenceCloudConfig spec and extracts configuration values.
        Uses unified 'sources.confluence' namespace (Cloud vs Server detected from URL).
        
        Args:
            config_service: ConfigService instance with config loaded.
            
        Returns:
            Configured ConfluenceCloudConnector instance.
            
        Raises:
            ValueError: If required config values are missing.
            
        Examples:
            >>> from indexed_config import ConfigService
            >>> config = ConfigService()
            >>> connector = ConfluenceCloudConnector.from_config(config)
        """
        # Register our config spec using unified namespace
        config_service.register(ConfluenceCloudConfig, path="sources.confluence.cloud")
        
        # Bind and get our config
        provider = config_service.bind()
        cfg = provider.get(ConfluenceCloudConfig)
        
        # Create instance with config values
        return cls(
            url=cfg.url,
            query=cfg.query,
            email=cfg.get_email(),
            api_token=cfg.get_api_token(),
            read_all_comments=cfg.read_all_comments,
        )


__all__ = ["ConfluenceConnector", "ConfluenceCloudConnector"]
