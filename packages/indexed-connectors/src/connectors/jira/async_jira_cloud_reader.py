"""Async Jira Cloud document reader using httpx for concurrent requests.

Sequential JQL search via Enhanced JQL API (cursor pagination), then async
concurrent attachment downloads when enabled.
"""

import asyncio
from base64 import b64encode
from typing import Any

import httpx
import requests
from loguru import logger
from utils.retry import execute_with_retry


class JiraCloudAPIError(Exception):
    """Raised when the Jira Cloud API returns an error response."""

    def __init__(self, status_code: int, message: str, url: str) -> None:
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"Jira Cloud API error {status_code} at {url}: {message}")


class AsyncJiraCloudDocumentReader:
    """Jira Cloud reader that uses sequential search and async attachment fetching.

    Issue listing uses the Enhanced JQL API with nextPageToken pagination.
    Attachment downloads run concurrently via httpx when enabled.
    """

    def __init__(
        self,
        base_url: str,
        query: str,
        email: str,
        api_token: str,
        batch_size: int = 500,
        number_of_retries: int = 3,
        retry_delay: int = 1,
        max_skipped_items_in_row: int = 5,
        max_concurrent_requests: int = 10,
        include_attachments: bool = False,
        max_attachment_size_mb: int = 10,
    ):
        if not email or not api_token:
            raise ValueError(
                "Cloud authentication requires both 'email' and 'api_token'"
            )
        from .._url_guard import is_cloud_host

        if not is_cloud_host(base_url):
            raise ValueError("Cloud URLs must end with .atlassian.net")

        self.base_url = base_url
        self.query = query
        self.email = email
        self.api_token = api_token
        self.batch_size = batch_size
        self.number_of_retries = number_of_retries
        self.retry_delay = retry_delay
        self.max_skipped_items_in_row = max_skipped_items_in_row
        self.max_concurrent_requests = max_concurrent_requests
        self.include_attachments = include_attachments
        self.max_attachment_size_bytes = max_attachment_size_mb * 1024 * 1024
        self.fields = (
            "summary,description,comment,attachment,updated"
            if include_attachments
            else "summary,description,comment,updated"
        )
        self._auth_header = self._build_auth_header(email, api_token)
        self._json_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._auth_header,
        }

    @staticmethod
    def _build_auth_header(email: str, api_token: str) -> str:
        credentials = b64encode(f"{email}:{api_token}".encode()).decode()
        return f"Basic {credentials}"

    def read_all_documents(self) -> list[dict[str, Any]]:
        """Read all documents: sequential JQL search, then optional attachments."""
        issues = self._read_issues_sync()
        if not self.include_attachments:
            return issues
        return asyncio.run(self._enrich_with_attachments(issues))

    def get_number_of_documents(self) -> int:
        """Get approximate count of documents matching the query."""
        return self._get_approximate_count()

    def get_reader_details(self) -> dict[str, Any]:
        """Return reader configuration metadata for diagnostics."""
        return {
            "type": "jiraCloud",
            "baseUrl": self.base_url,
            "query": self.query,
            "batchSize": self.batch_size,
            "fields": self.fields,
        }

    def _read_issues_sync(self) -> list[dict[str, Any]]:
        """Fetch all issues via sequential nextPageToken pagination."""
        issues: list[dict[str, Any]] = []
        next_token: str | None = None

        while True:
            body: dict[str, Any] = {
                "jql": self.query,
                "fields": self.fields.split(","),
                "maxResults": self.batch_size,
            }
            if next_token:
                body["nextPageToken"] = next_token

            result = self._post_with_retry(
                f"{self.base_url}/rest/api/3/search/jql",
                body,
            )
            page_issues = result.get("issues", [])
            issues.extend(page_issues)

            next_token = result.get("nextPageToken")
            if not next_token:
                break

        return issues

    def _get_approximate_count(self) -> int:
        """POST /rest/api/3/search/approximate-count for issue count estimate."""
        result = self._post_with_retry(
            f"{self.base_url}/rest/api/3/search/approximate-count",
            {"jql": self.query},
        )
        return int(result.get("count", 0))

    def _post_with_retry(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST with retry on transient/rate-limit errors."""

        def do_request() -> dict[str, Any]:
            response = requests.post(
                url,
                headers=self._json_headers,
                json=body,
                timeout=(5, 30),
            )
            self._raise_for_status(response)
            return response.json()

        return execute_with_retry(
            do_request,
            f"POST {url}",
            self.number_of_retries,
            self.retry_delay,
        )

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        """Raise JiraCloudAPIError for non-success HTTP responses."""
        if response.ok:
            return
        message = "Unknown error"
        try:
            error_body = response.json()
            if "errorMessages" in error_body:
                message = "; ".join(error_body["errorMessages"])
            elif "message" in error_body:
                message = str(error_body["message"])
        except Exception:
            message = response.text[:500] if response.text else message
        raise JiraCloudAPIError(
            status_code=response.status_code,
            message=message,
            url=str(response.url),
        )

    async def _enrich_with_attachments(
        self, issues: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Download attachment bytes for all issues concurrently."""
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        # Atlassian Cloud serves attachment bytes via a 302 redirect to a
        # media/S3 CDN — follow_redirects=True is required or every
        # attachment download fails on the redirect (D1). The CDN is a
        # legitimate off-origin host, so _url_guard is deliberately not
        # applied to this client (see .spec/tech-connectors.md § Credential Security).
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.max_concurrent_requests,
                max_keepalive_connections=5,
            ),
        ) as client:
            for issue in issues:
                att_meta = issue.get("fields", {}).get("attachment", [])
                downloaded: list[dict[str, Any]] = []
                for att in att_meta:
                    size = att.get("size", 0)
                    if size > self.max_attachment_size_bytes:
                        logger.warning(
                            f"Skipping attachment {att.get('filename')} "
                            f"({size / 1024 / 1024:.1f} MB) — exceeds limit"
                        )
                        continue
                    data = await self._fetch_attachment_bytes(
                        client, semaphore, att["content"]
                    )
                    if data:
                        downloaded.append(
                            {
                                "filename": att.get("filename", "unknown"),
                                "bytes": data,
                                "mimeType": att.get("mimeType", ""),
                            }
                        )
                issue["attachments"] = downloaded

        return issues

    async def _fetch_attachment_bytes(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        url: str,
    ) -> bytes | None:
        """Download a single attachment."""
        async with semaphore:
            try:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": self._auth_header,
                        "Accept": "application/octet-stream",
                    },
                )
                # The 302 to the CDN is already followed by the client above;
                # only a real (4xx/5xx) failure should short-circuit here (D1).
                if not response.is_success:
                    logger.warning(
                        f"Failed to download attachment {url}: "
                        f"HTTP {response.status_code}"
                    )
                    return None
                return response.content
            except Exception as e:
                logger.warning(f"Failed to download attachment {url}: {e}")
                return None
