"""Jira connector for indexing Jira issues.

This connector wraps the existing JiraDocumentReader and JiraDocumentConverter
to provide a standardized BaseConnector interface for both Jira Server/Data Center
and Jira Cloud.
"""

from typing import ClassVar, Optional
from core.v1.connectors.metadata import ConnectorMetadata
from .jira_document_reader import JiraDocumentReader
from .unified_jira_document_converter import UnifiedJiraDocumentConverter
from .async_jira_cloud_reader import AsyncJiraCloudDocumentReader
from .schema import JiraConfig, JiraCloudConfig


class JiraConnector:
    # Metadata for CLI generation and compatibility
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="jira",
        display_name="Jira (Server/Data Center)",
        description="Index Jira issues using JQL queries (token or basic auth)",
        config_class=JiraConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create --type jira --name issues",
    )
    """Connector for Jira Server/Data Center issues.

    Discovers and indexes Jira issues based on JQL queries. Supports both
    token-based and username/password authentication.

    Attributes:
        reader: JiraDocumentReader instance for API calls
        converter: JiraDocumentConverter instance for format conversion

    Examples:
        >>> # Token authentication (recommended)
        >>> connector = JiraConnector(
        ...     url="https://jira.example.com",
        ...     query="project = PROJ AND created >= -30d",
        ...     token="your-token"
        ... )
        >>> index.add_collection("jira-issues", connector)
        >>>
        >>> # Username/password authentication
        >>> connector = JiraConnector(
        ...     url="https://jira.example.com",
        ...     query="assignee = currentUser()",
        ...     login="username",
        ...     password="password"
        ... )
    """

    def __init__(
        self,
        url: str,
        query: str,
        token: Optional[str] = None,
        login: Optional[str] = None,
        password: Optional[str] = None,
        include_attachments: bool = False,
        max_chunk_tokens: int = 512,
        ocr_enabled: bool = True,
        max_attachment_size_mb: int = 10,
    ):
        """Initialize Jira Server/Data Center connector.

        Args:
            url: Jira base URL (e.g., https://jira.example.com)
            query: JQL query to filter issues
            token: Bearer token for authentication (recommended)
            login: Username for basic auth (if token not provided)
            password: Password for basic auth (if token not provided)
            include_attachments: Fetch and parse issue attachments.
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

        # Initialize reader and converter
        self._reader = JiraDocumentReader(
            base_url=url,
            query=query,
            token=token,
            login=login,
            password=password,
            include_attachments=include_attachments,
            max_attachment_size_mb=max_attachment_size_mb,
        )
        self._converter = UnifiedJiraDocumentConverter(
            max_chunk_tokens=max_chunk_tokens,
            ocr=ocr_enabled,
            include_attachments=include_attachments,
        )

    @property
    def reader(self) -> JiraDocumentReader:
        """Return the document reader instance."""
        return self._reader

    @property
    def converter(self) -> UnifiedJiraDocumentConverter:
        """Return the document converter instance."""
        return self._converter

    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "jira"

    def __repr__(self) -> str:
        """String representation of connector."""
        return f"JiraConnector(url='{self._url}', query='{self._query}')"

    # --- Config integration ---
    @classmethod
    def config_spec(cls) -> dict:
        """
        Configuration schema for the Jira (Server/Data Center) connector.

        Provides the expected configuration keys and their metadata: "url" (Jira server URL), "query" (JQL query), and authentication alternatives via environment variable names "token_env" (API token) or "login_env" and "password_env" (basic auth). Each key maps to a dictionary describing type, requirement, secrecy, and defaults where applicable.

        Returns:
            dict: Mapping of configuration keys to their schema definitions.
        """
        return {
            "url": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Jira URL (Server/Data Center)",
            },
            "query": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Base JQL query",
            },
            # Auth alternatives (token OR login+password)
            "token_env": {
                "type": "str",
                "required": False,
                "secret": True,
                "default": "JIRA_TOKEN",
                "description": "Env var name containing API token",
            },
            "login_env": {
                "type": "str",
                "required": False,
                "secret": True,
                "default": "JIRA_LOGIN",
                "description": "Env var name for basic auth username",
            },
            "password_env": {
                "type": "str",
                "required": False,
                "secret": True,
                "default": "JIRA_PASSWORD",
                "description": "Env var name for basic auth password",
            },
        }

    @classmethod
    def from_config(cls, config_service) -> "JiraConnector":
        """
        Create a JiraConnector using configuration from a ConfigService.

        Registers the JiraConfig schema at "sources.jira", binds the service, reads the Jira configuration, and returns a JiraConnector initialized from those configuration values.

        Parameters:
            config_service (ConfigService): Service providing configuration; must expose JiraConfig at the "sources.jira" path.

        Returns:
            JiraConnector: A connector configured with values from the retrieved JiraConfig.
        """
        # Register our config spec
        config_service.register(JiraConfig, path="sources.jira")

        # Bind and get our config
        provider = config_service.bind()
        cfg = provider.get(JiraConfig)

        # Create instance with config values
        return cls(
            url=cfg.url,
            query=cfg.query,
            token=cfg.get_token(),
            login=cfg.get_login(),
            password=cfg.get_password(),
            include_attachments=cfg.include_attachments,
            max_chunk_tokens=cfg.max_chunk_tokens,
            ocr_enabled=cfg.ocr_enabled,
            max_attachment_size_mb=cfg.max_attachment_size_mb,
        )


class JiraCloudConnector:
    # Metadata for CLI generation and compatibility
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="jiraCloud",
        display_name="Jira Cloud",
        description="Index Jira Cloud issues via Atlassian Cloud API",
        config_class=JiraCloudConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create --type jiraCloud --name issues",
    )
    """Connector for Jira Cloud issues.

    Discovers and indexes Jira Cloud issues using Atlassian Cloud API.
    Requires email and API token for authentication.

    Attributes:
        reader: JiraCloudDocumentReader instance for API calls
        converter: JiraCloudDocumentConverter instance for format conversion

    Examples:
        >>> connector = JiraCloudConnector(
        ...     url="https://company.atlassian.net",
        ...     query="project = PROJ",
        ...     email="user@example.com",
        ...     api_token="your-api-token"
        ... )
        >>> index.add_collection("jira-cloud", connector)
    """

    def __init__(
        self,
        url: str,
        query: str,
        email: str,
        api_token: str,
        include_attachments: bool = False,
        max_chunk_tokens: int = 512,
        ocr_enabled: bool = True,
        max_attachment_size_mb: int = 10,
    ):
        """Initialize Jira Cloud connector.

        Args:
            url: Jira Cloud URL (e.g., https://company.atlassian.net)
            query: JQL query to filter issues
            email: Atlassian account email
            api_token: Atlassian API token
            include_attachments: Fetch and parse issue attachments.
            max_chunk_tokens: Max tokens per chunk for ParsingModule.
            ocr_enabled: Enable OCR for image attachments.
            max_attachment_size_mb: Max attachment size in MB to download.
        """
        self._url = url
        self._query = query

        # Use async reader for concurrent batch fetching
        self._reader = AsyncJiraCloudDocumentReader(
            base_url=url,
            query=query,
            email=email,
            api_token=api_token,
            include_attachments=include_attachments,
            max_attachment_size_mb=max_attachment_size_mb,
        )
        self._converter = UnifiedJiraDocumentConverter(
            max_chunk_tokens=max_chunk_tokens,
            ocr=ocr_enabled,
            include_attachments=include_attachments,
        )

    @property
    def reader(self) -> AsyncJiraCloudDocumentReader:
        """Return the document reader instance."""
        return self._reader

    @property
    def converter(self) -> UnifiedJiraDocumentConverter:
        """Return the document converter instance."""
        return self._converter

    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "jiraCloud"

    def __repr__(self) -> str:
        """
        Return a concise string identifying the JiraCloudConnector instance.

        Returns:
            str: String in the form "JiraCloudConnector(url='<base_url>', query='<jql_query>')".
        """
        return f"JiraCloudConnector(url='{self._url}', query='{self._query}')"

    # --- Config integration ---
    @classmethod
    def config_spec(cls) -> dict:
        """
        Provide the configuration schema used to construct a JiraCloudConnector.

        Returns:
            A dictionary mapping configuration keys to their schema definitions:
            - `url`: Jira Cloud base URL (e.g., `https://company.atlassian.net`), required.
            - `query`: Base JQL query, required.
            - `email`: Atlassian account email used for authentication, required.
            - `api_token_env`: Name of the environment variable that contains the Atlassian API token, required, secret, defaults to `"ATLASSIAN_TOKEN"`.
        """
        return {
            "url": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Jira Cloud URL (e.g., https://company.atlassian.net)",
            },
            "query": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Base JQL query",
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
        }

    @classmethod
    def from_config(cls, config_service) -> "JiraCloudConnector":
        """
        Create a JiraCloudConnector configured from a ConfigService.

        Registers the JiraCloudConfig at path "sources.jira", binds the service, and constructs a JiraCloudConnector using values from the bound configuration.

        Parameters:
            config_service: ConfigService providing configuration data.

        Returns:
            JiraCloudConnector: Configured connector instance.
        """
        # Register our config spec using unified namespace
        config_service.register(JiraCloudConfig, path="sources.jira")

        # Bind and get our config
        provider = config_service.bind()
        cfg = provider.get(JiraCloudConfig)

        # Create instance with config values
        return cls(
            url=cfg.url,
            query=cfg.query,
            email=cfg.get_email(),
            api_token=cfg.get_api_token(),
            include_attachments=cfg.include_attachments,
            max_chunk_tokens=cfg.max_chunk_tokens,
            ocr_enabled=cfg.ocr_enabled,
            max_attachment_size_mb=cfg.max_attachment_size_mb,
        )


__all__ = ["JiraConnector", "JiraCloudConnector"]
