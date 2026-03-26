"""Unified Jira document reader supporting both Cloud and Server/DC instances.

This module consolidates the previously separate JiraCloudDocumentReader and
JiraDocumentReader into a single parameterized class, following DRY principles.
"""

from enum import Enum
from typing import Optional
from atlassian import Jira

from utils.retry import execute_with_retry
from utils.batch import read_items_in_batches


class JiraAuthType(str, Enum):
    """Authentication type for Jira connection."""

    CLOUD = "cloud"
    SERVER_TOKEN = "server_token"
    SERVER_CREDENTIALS = "server_credentials"


class UnifiedJiraDocumentReader:
    """Unified reader for Jira Cloud and Server/DC with parameterized auth.

    This class replaces the separate JiraCloudDocumentReader and JiraDocumentReader
    classes, consolidating ~95% duplicate code into a single implementation.

    Args:
        base_url: Base URL of the Jira instance
        query: JQL query to fetch issues
        auth_type: Type of authentication to use (cloud, server_token, server_credentials)
        email: Email for Cloud authentication (required if auth_type=CLOUD)
        api_token: API token for Cloud authentication (required if auth_type=CLOUD)
        token: Personal Access Token for Server (required if auth_type=SERVER_TOKEN)
        login: Username for Server credentials auth (required if auth_type=SERVER_CREDENTIALS)
        password: Password for Server credentials auth (required if auth_type=SERVER_CREDENTIALS)
        batch_size: Number of issues to fetch per batch (default: 500)
        number_of_retries: Number of retry attempts on failure (default: 3)
        retry_delay: Delay in seconds between retries (default: 1)
        max_skipped_items_in_row: Max consecutive items to skip before failing (default: 5)

    Example:
        # Cloud authentication
        reader = UnifiedJiraDocumentReader(
            base_url="https://example.atlassian.net",
            query="project = PROJ",
            auth_type=JiraAuthType.CLOUD,
            email="user@example.com",
            api_token="token123"
        )

        # Server token authentication
        reader = UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",
            query="project = PROJ",
            auth_type=JiraAuthType.SERVER_TOKEN,
            token="token123"
        )

        # Server credentials authentication
        reader = UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",
            query="project = PROJ",
            auth_type=JiraAuthType.SERVER_CREDENTIALS,
            login="username",
            password="password"
        )
    """

    def __init__(
        self,
        base_url: str,
        query: str,
        auth_type: JiraAuthType = JiraAuthType.CLOUD,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        token: Optional[str] = None,
        login: Optional[str] = None,
        password: Optional[str] = None,
        batch_size: int = 500,
        number_of_retries: int = 3,
        retry_delay: int = 1,
        max_skipped_items_in_row: int = 5,
        include_attachments: bool = False,
        max_attachment_size_mb: int = 10,
    ):
        """Initialize the unified Jira document reader."""
        # Validate authentication parameters
        self._validate_auth(auth_type, email, api_token, token, login, password)

        # Validate URL format matches auth type
        self._validate_url(base_url, auth_type)

        # Store configuration
        self.base_url = base_url
        self.query = query
        self.auth_type = auth_type
        self.email = email
        self.api_token = api_token
        self.token = token
        self.login = login
        self.password = password
        self.batch_size = batch_size
        self.number_of_retries = number_of_retries
        self.retry_delay = retry_delay
        self.max_skipped_items_in_row = max_skipped_items_in_row
        self.include_attachments = include_attachments
        self.max_attachment_size_bytes = max_attachment_size_mb * 1024 * 1024
        self.fields = (
            "summary,description,comment,attachment,updated"
            if include_attachments
            else "summary,description,comment,updated"
        )

        # Initialize Jira client based on auth type
        self._client = self._create_client()

    @staticmethod
    def _validate_auth(
        auth_type: JiraAuthType,
        email: Optional[str],
        api_token: Optional[str],
        token: Optional[str],
        login: Optional[str],
        password: Optional[str],
    ) -> None:
        """Validate auth parameters for the chosen auth type.

        Raises:
            ValueError: If required authentication parameters are missing
        """
        if auth_type == JiraAuthType.CLOUD:
            if not email or not api_token:
                raise ValueError(
                    "Cloud authentication requires both 'email' and 'api_token'"
                )
        elif auth_type == JiraAuthType.SERVER_TOKEN:
            if not token:
                raise ValueError("Token authentication requires 'token'")
        elif auth_type == JiraAuthType.SERVER_CREDENTIALS:
            if not login or not password:
                raise ValueError(
                    "Credential authentication requires both 'login' and 'password'"
                )

    @staticmethod
    def _validate_url(base_url: str, auth_type: JiraAuthType) -> None:
        """Validate URL format matches auth type.

        Raises:
            ValueError: If URL format doesn't match the auth type
        """
        is_cloud_url = base_url.endswith(".atlassian.net")

        if auth_type == JiraAuthType.CLOUD and not is_cloud_url:
            raise ValueError(
                "Cloud URLs must end with .atlassian.net (e.g., https://example.atlassian.net)"
            )

        if (
            auth_type
            in (
                JiraAuthType.SERVER_TOKEN,
                JiraAuthType.SERVER_CREDENTIALS,
            )
            and is_cloud_url
        ):
            raise ValueError(
                "Server/DC URLs should not end with .atlassian.net. "
                "Use your on-premise Jira URL instead."
            )

    def _create_client(self) -> Jira:
        """Create Jira client based on auth type.

        Returns:
            Configured Jira client instance
        """
        if self.auth_type == JiraAuthType.CLOUD:
            return Jira(
                url=self.base_url,
                username=self.email,
                password=self.api_token,
                cloud=True,
            )
        elif self.auth_type == JiraAuthType.SERVER_TOKEN:
            return Jira(url=self.base_url, token=self.token)
        else:  # SERVER_CREDENTIALS
            return Jira(
                url=self.base_url,
                username=self.login,
                password=self.password,
                cloud=False,
            )

    def read_all_documents(self):
        """Read all documents matching the JQL query.

        When include_attachments is enabled, each issue dict gets an
        ``attachments`` key with a list of ``{filename, bytes, mimeType}`` dicts.

        Returns:
            List of Jira issues as dictionaries
        """
        issues = self.__read_items()
        if not self.include_attachments:
            return issues

        enriched = []
        for issue in issues:
            att_meta = issue.get("fields", {}).get("attachment", [])
            downloaded: list[dict] = []
            for att in att_meta:
                size = att.get("size", 0)
                if size > self.max_attachment_size_bytes:
                    from loguru import logger

                    logger.warning(
                        f"Skipping attachment {att.get('filename')} "
                        f"({size / 1024 / 1024:.1f} MB) — exceeds limit"
                    )
                    continue
                data = self._fetch_attachment_bytes(att["content"])
                if data:
                    downloaded.append(
                        {
                            "filename": att.get("filename", "unknown"),
                            "bytes": data,
                            "mimeType": att.get("mimeType", ""),
                        }
                    )
            issue["attachments"] = downloaded
            enriched.append(issue)
        return enriched

    def _fetch_attachment_bytes(self, url: str) -> bytes | None:
        """Download attachment bytes using the Jira client session."""
        try:
            import requests as req

            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            auth = (
                (self.login, self.password)
                if self.login and self.password
                else (self.email, self.api_token)
                if self.email and self.api_token
                else None
            )
            response = req.get(url, headers=headers, auth=auth, timeout=60)
            response.raise_for_status()
            return response.content
        except Exception:
            from loguru import logger

            logger.warning(f"Failed to download attachment: {url}")
            return None

    def get_number_of_documents(self) -> int:
        """Get the total count of documents matching the query.

        Returns:
            Total number of issues matching the JQL query
        """

        def do_request():
            # Use jql with limit=1 to get total count efficiently
            result = self._client.jql(self.query, fields=self.fields, start=0, limit=1)
            return result.get("total", 0)

        return execute_with_retry(
            do_request,
            f"Getting document count for query: {self.query}",
            self.number_of_retries,
            self.retry_delay,
        )

    def get_reader_details(self) -> dict:
        """Get reader configuration details.

        Returns:
            Dictionary containing reader type and configuration
        """
        # Use appropriate type based on auth type
        reader_type = "jiraCloud" if self.auth_type == JiraAuthType.CLOUD else "jira"

        return {
            "type": reader_type,
            "baseUrl": self.base_url,
            "query": self.query,
            "batchSize": self.batch_size,
            "fields": self.fields,
        }

    def __read_items(self):
        """Read items in batches using the batch utility."""

        def read_batch_func(start_at, batch_size):
            return self.__request_items(start_at=start_at, max_results=batch_size)

        return read_items_in_batches(
            read_batch_func,
            fetch_items_from_result_func=lambda result: result["issues"],
            fetch_total_from_result_func=lambda result: result["total"],
            batch_size=self.batch_size,
            max_skipped_items_in_row=self.max_skipped_items_in_row,
        )

    def __request_items(self, start_at: int, max_results: int):
        """Request a batch of items from Jira.

        Args:
            start_at: Starting index for pagination
            max_results: Maximum number of results to return

        Returns:
            Dictionary with 'issues' and 'total' keys
        """

        def do_request():
            result = self._client.jql(
                self.query,
                fields=self.fields,
                start=start_at,
                limit=max_results,
            )
            return {
                "issues": result.get("issues", []),
                "total": result.get("total", 0),
            }

        return execute_with_retry(
            do_request,
            f"Requesting items at {start_at} with max {max_results}",
            self.number_of_retries,
            self.retry_delay,
        )
