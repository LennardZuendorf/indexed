"""Async Jira Cloud document reader using httpx for concurrent requests.

Fetches the issue list via JQL (sequential, paginated), then fetches
individual issue details concurrently for faster indexing.
"""

import asyncio
from base64 import b64encode

import httpx
from loguru import logger


class AsyncJiraCloudDocumentReader:
    """Jira Cloud reader that uses async HTTP for concurrent issue fetching.

    The initial JQL search is paginated sequentially, but individual issue
    detail fetching can be parallelized when fetching additional fields.
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
    ):
        if not email or not api_token:
            raise ValueError(
                "Cloud authentication requires both 'email' and 'api_token'"
            )
        if not base_url.endswith(".atlassian.net"):
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
        self.fields = "summary,description,comment,updated"
        self._auth_header = self._build_auth_header(email, api_token)

    @staticmethod
    def _build_auth_header(email: str, api_token: str) -> str:
        credentials = b64encode(f"{email}:{api_token}".encode()).decode()
        return f"Basic {credentials}"

    def read_all_documents(self):
        """Read all documents using async batch fetching."""
        return asyncio.run(self._read_all_async())

    def get_number_of_documents(self) -> int:
        """Get total count of documents matching the query."""
        import requests

        response = requests.get(
            url=f"{self.base_url}/rest/api/3/search",
            headers={
                "Accept": "application/json",
                "Authorization": self._auth_header,
            },
            params={
                "jql": self.query,
                "fields": self.fields,
                "startAt": 0,
                "maxResults": 1,
            },
        )
        response.raise_for_status()
        return response.json().get("total", 0)

    def get_reader_details(self) -> dict:
        return {
            "type": "jiraCloud",
            "baseUrl": self.base_url,
            "query": self.query,
            "batchSize": self.batch_size,
            "fields": self.fields,
        }

    async def _read_all_async(self) -> list:
        """Fetch all issues using concurrent batch requests."""
        # First, get total count
        total = 0
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        async with httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=self.max_concurrent_requests,
                max_keepalive_connections=5,
            ),
        ) as client:
            # Get total count first
            total = await self._get_total(client)
            if total == 0:
                return []

            # Create tasks for all batches
            batch_offsets = list(range(0, total, self.batch_size))
            tasks = [
                self._fetch_batch(client, semaphore, offset) for offset in batch_offsets
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_issues = []
        skipped = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    f"Failed to fetch batch at offset {batch_offsets[i]}: {result}"
                )
                skipped += 1
                if skipped > self.max_skipped_items_in_row:
                    raise result
            else:
                all_issues.extend(result)

        return all_issues

    async def _get_total(self, client: httpx.AsyncClient) -> int:
        """Get total issue count for the JQL query."""
        response = await client.get(
            f"{self.base_url}/rest/api/3/search",
            headers={
                "Accept": "application/json",
                "Authorization": self._auth_header,
            },
            params={
                "jql": self.query,
                "fields": self.fields,
                "startAt": 0,
                "maxResults": 1,
            },
        )
        response.raise_for_status()
        return response.json().get("total", 0)

    async def _fetch_batch(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        offset: int,
    ) -> list:
        """Fetch a batch of issues at the given offset."""
        async with semaphore:
            for attempt in range(self.number_of_retries):
                try:
                    response = await client.get(
                        f"{self.base_url}/rest/api/3/search",
                        headers={
                            "Accept": "application/json",
                            "Authorization": self._auth_header,
                        },
                        params={
                            "jql": self.query,
                            "fields": self.fields,
                            "startAt": offset,
                            "maxResults": self.batch_size,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    return data.get("issues", [])
                except Exception as e:
                    if attempt == self.number_of_retries - 1:
                        raise
                    logger.debug(
                        f"Retry {attempt + 1} for batch at offset {offset}: {e}"
                    )
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        return []
