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
from .unified_confluence_document_converter import UnifiedConfluenceDocumentConverter
from .async_confluence_cloud_reader import AsyncConfluenceCloudDocumentReader
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
        include_attachments: bool = False,
        max_chunk_tokens: int = 512,
        ocr_enabled: bool = True,
        max_attachment_size_mb: int = 10,
    ):
        """Initialize Confluence Server/Data Center connector.

        Args:
            url: Confluence base URL (e.g., https://confluence.example.com)
            query: CQL query to filter pages
            token: Bearer token for authentication (recommended)
            login: Username for basic auth (if token not provided)
            password: Password for basic auth (if token not provided)
            read_all_comments: Read all nested comments (default: True).
            include_attachments: Fetch and parse page attachments.
            max_chunk_tokens: Max tokens per chunk for ParsingModule.
            ocr_enabled: Enable OCR for image attachments.
            max_attachment_size_mb: Max attachment size in MB to download.

        Raises:
            ValueError: If neither token nor login/password are provided
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
            include_attachments=include_attachments,
            max_attachment_size_mb=max_attachment_size_mb,
        )
        self._converter = UnifiedConfluenceDocumentConverter(
            is_cloud=False,
            max_chunk_tokens=max_chunk_tokens,
            ocr=ocr_enabled,
            include_attachments=include_attachments,
        )

    @property
    def reader(self) -> ConfluenceDocumentReader:
        """Return the document reader instance."""
        return self._reader

    @property
    def converter(self) -> UnifiedConfluenceDocumentConverter:
        """Return the document converter instance."""
        return self._converter

    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "confluence"

    def __repr__(self) -> str:
        """
        Provide a concise developer-focused string identifying this connector instance.

        Returns:
            str: Representation containing the connector type along with its configured base URL and CQL query.
        """
        return f"ConfluenceConnector(url='{self._url}', query='{self._query}')"

    # --- Configuration integration ---
    @classmethod
    def config_spec(cls) -> dict:
        """
        Configuration specification for the Confluence Server/Data Center connector.

        Returns:
            dict: Mapping of configuration option names to their schema. Includes:
                - "base_url": Confluence base URL (required).
                - "query": Base CQL query (required).
                - "token_env": Environment variable name for an API token (optional, secret).
                - "login_env": Environment variable name for basic auth username (optional, secret).
                - "password_env": Environment variable name for basic auth password (optional, secret).
                - "read_all_comments": Whether to read nested comments instead of only top-level comments (optional, defaults to True).
        """
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
        """
        Create a ConfluenceConnector using values from a ConfigService.

        Registers the ConfluenceConfig schema at "sources.confluence", binds the provider to retrieve the configured ConfluenceConfig, and constructs a ConfluenceConnector populated from that configuration.

        Parameters:
            config_service: ConfigService that provides access to registered configuration values.

        Returns:
            ConfluenceConnector: An instance configured with values from ConfluenceConfig.
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
            include_attachments=cfg.include_attachments,
            max_chunk_tokens=cfg.max_chunk_tokens,
            ocr_enabled=cfg.ocr_enabled,
            max_attachment_size_mb=cfg.max_attachment_size_mb,
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
        include_attachments: bool = False,
        max_chunk_tokens: int = 512,
        ocr_enabled: bool = True,
        max_attachment_size_mb: int = 10,
    ):
        """Initialize Confluence Cloud connector.

        Args:
            url: Confluence Cloud URL (e.g., https://company.atlassian.net/wiki)
            query: CQL query to filter pages
            email: Atlassian account email
            api_token: Atlassian API token
            read_all_comments: Read all nested comments (default: True).
            include_attachments: Fetch and parse page attachments.
            max_chunk_tokens: Max tokens per chunk for ParsingModule.
            ocr_enabled: Enable OCR for image attachments.
            max_attachment_size_mb: Max attachment size in MB to download.
        """
        self._url = url
        self._query = query
        self._read_all_comments = read_all_comments

        # Use async reader for concurrent comment fetching
        self._reader = AsyncConfluenceCloudDocumentReader(
            base_url=url,
            query=query,
            email=email,
            api_token=api_token,
            read_all_comments=read_all_comments,
            include_attachments=include_attachments,
            max_attachment_size_mb=max_attachment_size_mb,
        )
        self._converter = UnifiedConfluenceDocumentConverter(
            is_cloud=True,
            max_chunk_tokens=max_chunk_tokens,
            ocr=ocr_enabled,
            include_attachments=include_attachments,
        )

    @property
    def reader(self) -> AsyncConfluenceCloudDocumentReader:
        """Return the document reader instance."""
        return self._reader

    @property
    def converter(self) -> UnifiedConfluenceDocumentConverter:
        """Return the document converter instance."""
        return self._converter

    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "confluenceCloud"

    def __repr__(self) -> str:
        """
        Provide a developer-focused string identifying the connector by base URL and CQL query.

        Returns:
            str: Representation in the form "ConfluenceCloudConnector(url='<base_url>', query='<cql_query>')".
        """
        return f"ConfluenceCloudConnector(url='{self._url}', query='{self._query}')"

    # --- Configuration integration ---
    @classmethod
    def config_spec(cls) -> dict:
        """
        Return the configuration specification for Confluence Cloud connector options.

        The returned dictionary maps configuration keys to their metadata: expected type, whether the key is required, whether it is secret, default value when applicable, and a short description.

        Returns:
            dict: Specification with these keys:
                - "base_url" (str): Confluence Cloud base URL (required).
                - "query" (str): Base CQL query to select pages (required).
                - "email" (str): Atlassian account email (required).
                - "api_token_env" (str): Environment variable name holding the API token (required, secret, default "ATLASSIAN_TOKEN").
                - "read_all_comments" (bool): Whether to read nested comments instead of only top-level comments (optional, default True).
        """
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
        """
        Create a ConfluenceCloudConnector from a ConfigService.

        Parameters:
            config_service (ConfigService): Config service providing a ConfluenceCloudConfig (expected under "sources.confluence").

        Returns:
            ConfluenceCloudConnector: Connector instance configured from the retrieved ConfluenceCloudConfig.
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
            include_attachments=cfg.include_attachments,
            max_chunk_tokens=cfg.max_chunk_tokens,
            ocr_enabled=cfg.ocr_enabled,
            max_attachment_size_mb=cfg.max_attachment_size_mb,
        )


__all__ = ["ConfluenceConnector", "ConfluenceCloudConnector"]
