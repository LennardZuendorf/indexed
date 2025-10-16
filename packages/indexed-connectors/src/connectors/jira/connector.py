"""Jira connector for indexing Jira issues.

This connector wraps the existing JiraDocumentReader and JiraDocumentConverter
to provide a standardized BaseConnector interface for both Jira Server/Data Center
and Jira Cloud.
"""

import os
from typing import ClassVar, Optional
from core.v1.connectors.metadata import ConnectorMetadata
from core.v1.config.settings import _get_env_var
from .jira_document_reader import JiraDocumentReader
from .jira_document_converter import JiraDocumentConverter
from .jira_cloud_document_reader import JiraCloudDocumentReader
from .jira_cloud_document_converter import JiraCloudDocumentConverter
from .schema import JiraConfig, JiraCloudConfig


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
    ):
        """Initialize Jira Server/Data Center connector.

        Args:
            url: Jira base URL (e.g., https://jira.example.com)
            query: JQL query to filter issues
            token: Bearer token for authentication (recommended)
            login: Username for basic auth (if token not provided)
            password: Password for basic auth (if token not provided)

        Raises:
            ValueError: If neither token nor login/password are provided

        Examples:
            >>> connector = JiraConnector(
            ...     url="https://jira.example.com",
            ...     query="project = MYPROJ",
            ...     token="bearer-token-here"
            ... )
        """
        if not token and (not login or not password):
            raise ValueError(
                "Either 'token' or both 'login' and 'password' must be provided"
            )

        self._url = url
        self._query = query

        # Initialize reader and converter
        self._reader = JiraDocumentReader(
            base_url=url, query=query, token=token, login=login, password=password
        )
        self._converter = JiraDocumentConverter()

    @property
    def reader(self) -> JiraDocumentReader:
        """Return the document reader instance."""
        return self._reader

    @property
    def converter(self) -> JiraDocumentConverter:
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
        return {
            "base_url": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Jira base URL (Server/Data Center)",
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
    def from_config(cls, config_service, namespace: str) -> "JiraConnector":
        settings = config_service.get()
        # Navigate by dotted path via getattr
        section = settings
        for part in namespace.split("."):
            section = getattr(section, part)
        # Expect dict-like attributes: base_url, query
        base_url = getattr(section, "base_url", None)
        query = getattr(section, "jql", None) or getattr(section, "query", None)
        if not base_url or not query:
            raise ValueError("Jira (Server/DC) config requires base_url and query")
        # Secrets via env - use safe getattr to handle MagicMock in tests
        token_env = _safe_str_attr(section, "token_env", "JIRA_TOKEN")
        login_env = _safe_str_attr(section, "login_env", "JIRA_LOGIN")
        password_env = _safe_str_attr(section, "password_env", "JIRA_PASSWORD")
        
        token = os.getenv(token_env) or _get_env_var(token_env)
        login = os.getenv(login_env) or _get_env_var(login_env)
        password = os.getenv(password_env) or _get_env_var(password_env)
        return cls(url=base_url, query=query, token=token, login=login, password=password)


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

    def __init__(self, url: str, query: str, email: str, api_token: str):
        """Initialize Jira Cloud connector.

        Args:
            url: Jira Cloud URL (e.g., https://company.atlassian.net)
            query: JQL query to filter issues
            email: Atlassian account email
            api_token: Atlassian API token (generate at
                      https://id.atlassian.com/manage/api-tokens)

        Examples:
            >>> connector = JiraCloudConnector(
            ...     url="https://mycompany.atlassian.net",
            ...     query="assignee = currentUser()",
            ...     email="me@example.com",
            ...     api_token="ATATT..."
            ... )
        """
        self._url = url
        self._query = query

        # Initialize reader and converter
        self._reader = JiraCloudDocumentReader(
            base_url=url, query=query, email=email, api_token=api_token
        )
        self._converter = JiraCloudDocumentConverter()

    @property
    def reader(self) -> JiraCloudDocumentReader:
        """Return the document reader instance."""
        return self._reader

    @property
    def converter(self) -> JiraCloudDocumentConverter:
        """Return the document converter instance."""
        return self._converter

    @property
    def connector_type(self) -> str:
        """Return connector type identifier."""
        return "jiraCloud"

    def __repr__(self) -> str:
        """String representation of connector."""
        return f"JiraCloudConnector(url='{self._url}', query='{self._query}')"

    # --- Config integration ---
    @classmethod
    def config_spec(cls) -> dict:
        return {
            "base_url": {
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
    def from_config(cls, config_service, namespace: str) -> "JiraCloudConnector":
        from core.v1.config.settings import _get_env_var

        settings = config_service.get()
        section = settings
        for part in namespace.split("."):
            section = getattr(section, part)
        base_url = getattr(section, "base_url", None)
        email = getattr(section, "email", None) or os.getenv("ATLASSIAN_EMAIL")
        query = getattr(section, "jql", None) or getattr(section, "query", None)
        if not base_url or not email or not query:
            raise ValueError("Jira Cloud config requires base_url, email, and query (jql)")
        # Secrets resolution: prefer ATLASSIAN_TOKEN, fallback to configured api_token_env
        token_env_name = _safe_str_attr(section, "api_token_env", "ATLASSIAN_TOKEN")
        api_token = os.getenv("ATLASSIAN_TOKEN") or _get_env_var(token_env_name)
        if not api_token:
            raise ValueError(
                "Missing Atlassian API token. Set ATLASSIAN_TOKEN or the configured api_token_env."
            )
        return cls(url=base_url, query=query, email=email, api_token=api_token)


__all__ = ["JiraConnector", "JiraCloudConnector"]
