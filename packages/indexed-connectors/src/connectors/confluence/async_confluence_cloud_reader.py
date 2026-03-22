"""Async Confluence Cloud document reader using httpx for concurrent requests.

Parallelizes page comment fetching to speed up indexing of Confluence Cloud
instances with many pages containing comments.
"""

import asyncio
from typing import Optional

import httpx
from loguru import logger

from .confluence_cloud_document_reader import (
    ConfluenceCloudAPIError,
    ConfluenceCloudDocumentReader,
)

# Window size for concurrent comment fetching to limit memory usage
_COMMENT_FETCH_WINDOW = 100


class AsyncConfluenceCloudDocumentReader:
    """Confluence Cloud reader that uses async HTTP for concurrent comment fetching.

    The page listing is done sequentially (Confluence API requires cursor-based
    pagination), but comment fetching for multiple pages is done concurrently
    in windows to limit memory usage.
    """

    def __init__(
        self,
        base_url: str,
        query: str,
        email: str,
        api_token: str,
        batch_size: int = 50,
        number_of_retries: int = 3,
        retry_delay: int = 1,
        max_skipped_items_in_row: int = 5,
        read_all_comments: bool = False,
        max_concurrent_requests: int = 10,
    ):
        if not email or not api_token:
            raise ValueError(
                "Both 'email' and 'api_token' must be provided for Confluence Cloud."
            )

        if not base_url.endswith(".atlassian.net"):
            raise ValueError(
                "Base URL must be a Confluence Cloud URL (ending with .atlassian.net)"
            )

        self.base_url = base_url
        self.query = ConfluenceCloudDocumentReader.build_page_query(query)
        self.email = email
        self.api_token = api_token
        self.batch_size = batch_size
        self.expand = (
            "content.body.storage,content.ancestors,content.version,content.children.comment"
            if read_all_comments
            else "content.body.storage,content.ancestors,content.version,content.children.comment.body.storage"
        )
        self.number_of_retries = number_of_retries
        self.retry_delay = retry_delay
        self.max_skipped_items_in_row = max_skipped_items_in_row
        self.read_all_comments = read_all_comments
        self.max_concurrent_requests = max_concurrent_requests

    def read_all_documents(self):
        """Read all documents, fetching comments concurrently in windows."""
        window = []
        for page in self._read_pages_sync():
            window.append(page)
            if len(window) >= _COMMENT_FETCH_WINDOW:
                yield from self._yield_pages_with_comments(window)
                window = []
        if window:
            yield from self._yield_pages_with_comments(window)

    def _yield_pages_with_comments(self, pages: list):
        """Fetch comments for a window of pages and yield results."""
        comments_map = asyncio.run(self._fetch_all_comments_async(pages))
        for i, page in enumerate(pages):
            yield {"page": page, "comments": comments_map.get(i, [])}

    def get_number_of_documents(self) -> int:
        import requests

        response = requests.get(
            url=f"{self.base_url}/wiki/rest/api/search",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            params={"cql": self.query, "limit": 1, "start": 0},
            auth=(self.email, self.api_token),
        )
        response.raise_for_status()
        return response.json()["totalSize"]

    def get_reader_details(self) -> dict:
        return {
            "type": "confluenceCloud",
            "baseUrl": self.base_url,
            "query": self.query,
            "expand": self.expand,
            "batchSize": self.batch_size,
            "readAllComments": self.read_all_comments,
        }

    def _read_pages_sync(self):
        """Read pages using sync requests (pagination is sequential by nature)."""
        import requests

        start_at = 0
        cursor: Optional[str] = None

        while True:
            params = {
                "cql": self.query,
                "limit": self.batch_size,
                "start": start_at,
                "expand": self.expand,
            }
            if cursor:
                params["cursor"] = cursor

            response = requests.get(
                url=f"{self.base_url}/wiki/rest/api/search",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                params=params,
                auth=(self.email, self.api_token),
            )
            try:
                response.raise_for_status()
            except Exception:
                error_message = "Unknown error"
                try:
                    error_body = response.json()
                    error_message = error_body.get("message", error_message)
                except Exception:
                    error_message = (
                        response.text[:500] if response.text else error_message
                    )
                raise ConfluenceCloudAPIError(
                    status_code=response.status_code,
                    reason=response.reason,
                    message=error_message,
                    url=response.url,
                )

            result = response.json()
            items = result.get("results", [])
            total = result.get("totalSize", 0)

            for item in items:
                yield item

            start_at += len(items)
            if start_at >= total:
                break

            cursor = ConfluenceCloudDocumentReader.parse_url_params(
                result.get("_links", {}).get("next", "")
            ).get("cursor", [None])[0]

    async def _fetch_all_comments_async(self, pages: list) -> dict:
        """Fetch comments for all pages concurrently using httpx."""
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        comments_map: dict = {}

        async with httpx.AsyncClient(
            auth=(self.email, self.api_token),
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=self.max_concurrent_requests,
                max_keepalive_connections=5,
            ),
        ) as client:
            tasks = [
                self._fetch_comments_for_page(client, semaphore, page) for page in pages
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"Failed to fetch comments for page {i}: {result}")
                    comments_map[i] = []
                else:
                    comments_map[i] = result

        return comments_map

    async def _fetch_comments_for_page(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        page: dict,
    ) -> list:
        """Fetch comments for a single page."""
        comment_size = (
            page.get("content", {})
            .get("children", {})
            .get("comment", {})
            .get("size", 0)
        )
        if comment_size == 0:
            return []

        if not self.read_all_comments:
            return (
                page.get("content", {})
                .get("children", {})
                .get("comment", {})
                .get("results", [])
            )

        content_id = page["content"]["id"]
        all_comments = []
        start = 0

        while True:
            async with semaphore:
                for attempt in range(self.number_of_retries):
                    try:
                        response = await client.get(
                            f"{self.base_url}/wiki/rest/api/content/{content_id}/child/comment",
                            params={
                                "limit": self.batch_size,
                                "start": start,
                                "expand": "body.storage",
                                "depth": "all",
                            },
                            headers={
                                "Accept": "application/json",
                                "Content-Type": "application/json",
                            },
                        )
                        response.raise_for_status()
                        break
                    except Exception as e:
                        if attempt == self.number_of_retries - 1:
                            raise
                        logger.debug(
                            f"Retry {attempt + 1} for comments of page {content_id}: {e}"
                        )
                        await asyncio.sleep(self.retry_delay * (attempt + 1))

            result = response.json()
            comments = result.get("results", [])
            total = result.get("size", 0)

            all_comments.extend(comments)
            start += len(comments)
            if start >= total:
                break

        return all_comments
