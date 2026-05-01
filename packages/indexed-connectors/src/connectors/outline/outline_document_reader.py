"""Async Outline Wiki document reader.

Sequential collection/document listing with concurrent body + attachment
fetching in windows of 100, mirroring AsyncConfluenceCloudDocumentReader.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger


# Window size for concurrent body + attachment fetching
_FETCH_WINDOW = 100

# Regex to find inline Outline attachment URLs in Markdown
# Matches: ![alt](https://<host>/api/attachments.redirect?id=<uuid>)
_INLINE_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\((https?://[^\s)]+/api/attachments\.redirect\?[^)]+)\)"
)


class OutlineAPIError(Exception):
    """Raised when the Outline API returns an error response."""

    def __init__(self, status_code: int, message: str, url: str) -> None:
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"Outline API error {status_code} at {url}: {message}")


class OutlineDocumentReader:
    """Reads documents from an Outline workspace (Cloud or self-hosted).

    Pages through collections.list → documents.list sequentially, then fetches
    document bodies and attachments concurrently in sliding windows of 100.

    Args:
        base_url: Outline base URL (e.g. https://app.getoutline.com).
        api_token: Bearer token for authentication.
        collection_ids: Restrict to specific collection IDs. None = all collections.
        batch_size: Documents per API page request.
        max_concurrent_requests: Max concurrent HTTP requests in the fetch window.
        include_attachments: Download and return attachment bytes.
        download_inline_images: Extract and download inline image URLs from Markdown.
        max_attachment_size_mb: Max size per attachment to download.
        number_of_retries: Max retry attempts per request.
        retry_delay: Base delay in seconds between retries (doubles each attempt).
        verify_ssl: Verify TLS certificates (set False for self-signed CAs).
    """

    def __init__(
        self,
        base_url: str,
        api_token: str,
        collection_ids: Optional[list[str]] = None,
        batch_size: int = 50,
        max_concurrent_requests: int = 10,
        include_attachments: bool = True,
        download_inline_images: bool = True,
        max_attachment_size_mb: int = 10,
        number_of_retries: int = 3,
        retry_delay: float = 1.0,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.collection_ids = collection_ids
        self.batch_size = batch_size
        self.max_concurrent_requests = max_concurrent_requests
        self.include_attachments = include_attachments
        self.download_inline_images = download_inline_images
        self.max_attachment_size_bytes = max_attachment_size_mb * 1024 * 1024
        self.number_of_retries = number_of_retries
        self.retry_delay = retry_delay
        self.verify_ssl = verify_ssl
        self._auth_headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_all_documents(self) -> Iterator[dict]:
        """Yield enriched documents from the Outline workspace.

        Each yielded dict has shape:
            {
                "document": <full Outline document dict>,
                "attachments": [{"filename": str, "bytes": bytes, "mimeType": str, "id": str}]
            }
        """
        window: list[dict] = []
        for stub in self._iter_document_stubs():
            window.append(stub)
            if len(window) >= _FETCH_WINDOW:
                yield from self._yield_window(window)
                window = []
        if window:
            yield from self._yield_window(window)

    def get_number_of_documents(self) -> int:
        """Return total document count across targeted collections."""
        import requests  # type: ignore[import-untyped]

        total = 0
        for cid in self._get_collection_ids_sync():
            offset = 0
            while True:
                resp = requests.post(
                    f"{self.base_url}/api/documents.list",
                    headers=self._auth_headers,
                    json={
                        "collectionId": cid,
                        "status": "published",
                        "limit": 1,
                        "offset": offset,
                    },
                    verify=self.verify_ssl,
                )
                resp.raise_for_status()
                data = resp.json()
                total += data.get("pagination", {}).get("total", 0)
                break
        return total

    def get_reader_details(self) -> dict:
        return {
            "type": "outline",
            "baseUrl": self.base_url,
            "collectionIds": self.collection_ids,
            "batchSize": self.batch_size,
            "includeAttachments": self.include_attachments,
        }

    # ------------------------------------------------------------------
    # Sequential listing
    # ------------------------------------------------------------------

    def _iter_document_stubs(self) -> Iterator[dict]:
        """Yield minimal document stubs (id, title, updatedAt, etc.) for all collections."""
        import requests  # type: ignore[import-untyped]

        for collection_id in self._get_collection_ids_sync():
            offset = 0
            logger.debug("Listing documents in collection {}", collection_id)
            while True:
                for attempt in range(self.number_of_retries):
                    try:
                        resp = requests.post(
                            f"{self.base_url}/api/documents.list",
                            headers=self._auth_headers,
                            json={
                                "collectionId": collection_id,
                                "status": "published",
                                "limit": self.batch_size,
                                "offset": offset,
                            },
                            verify=self.verify_ssl,
                        )
                        self._raise_for_status(resp)
                        break
                    except OutlineAPIError:
                        raise
                    except Exception as exc:
                        if attempt == self.number_of_retries - 1:
                            raise
                        logger.debug(
                            "Retry {}/{} listing docs: {}",
                            attempt + 1,
                            self.number_of_retries,
                            exc,
                        )
                        import time

                        time.sleep(self.retry_delay * (2**attempt))

                result = resp.json()
                docs = result.get("data", [])
                pagination = result.get("pagination", {})
                total = pagination.get("total", 0)

                for doc in docs:
                    yield doc

                offset += len(docs)
                if not docs or offset >= total:
                    break

    def _get_collection_ids_sync(self) -> list[str]:
        """Return collection IDs to index — from config or by listing all."""
        if self.collection_ids:
            return self.collection_ids

        import requests  # type: ignore[import-untyped]

        ids: list[str] = []
        offset = 0
        while True:
            resp = requests.post(
                f"{self.base_url}/api/collections.list",
                headers=self._auth_headers,
                json={"limit": 100, "offset": offset},
                verify=self.verify_ssl,
            )
            self._raise_for_status(resp)
            result = resp.json()
            collections = result.get("data", [])
            ids.extend(c["id"] for c in collections)
            pagination = result.get("pagination", {})
            offset += len(collections)
            if not collections or offset >= pagination.get("total", 0):
                break

        logger.info("Found {} Outline collections", len(ids))
        return ids

    # ------------------------------------------------------------------
    # Windowed async fetching
    # ------------------------------------------------------------------

    def _yield_window(self, stubs: list[dict]) -> Iterator[dict]:
        """Fetch full docs (and optionally attachments) for a window of stubs."""
        full_docs = asyncio.run(self._fetch_bodies_async(stubs))
        attachments_map: dict[int, list[dict]] = {}
        if self.include_attachments or self.download_inline_images:
            attachments_map = asyncio.run(self._fetch_attachments_async(full_docs))

        for i, doc in enumerate(full_docs):
            if doc is None:
                continue
            yield {
                "document": doc,
                "attachments": attachments_map.get(i, []),
            }

    async def _fetch_bodies_async(self, stubs: list[dict]) -> list[Optional[dict]]:
        """Fetch full document bodies for a list of stubs concurrently."""
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        async with httpx.AsyncClient(
            headers=self._auth_headers,
            timeout=30.0,
            verify=self.verify_ssl,
            limits=httpx.Limits(
                max_connections=self.max_concurrent_requests,
                max_keepalive_connections=5,
            ),
        ) as client:
            tasks = [self._fetch_body(client, semaphore, stub) for stub in stubs]
            return list(await asyncio.gather(*tasks))

    async def _fetch_body(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        stub: dict,
    ) -> Optional[dict]:
        """Fetch a single document's full body via documents.info."""
        doc_id = stub.get("id", "")
        async with semaphore:
            for attempt in range(self.number_of_retries):
                try:
                    resp = await client.post(
                        f"{self.base_url}/api/documents.info",
                        json={"id": doc_id},
                    )
                    resp.raise_for_status()
                    return dict(resp.json().get("data", {}))
                except Exception as exc:
                    if attempt == self.number_of_retries - 1:
                        logger.warning(
                            "Failed to fetch body for doc {}: {}", doc_id, exc
                        )
                        return None
                    await asyncio.sleep(self.retry_delay * (2**attempt))
        return None

    async def _fetch_attachments_async(
        self, docs: list[Optional[dict]]
    ) -> dict[int, list[dict]]:
        """Fetch and download attachments for all docs concurrently."""
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        attachments_map: dict[int, list[dict]] = {}

        async with httpx.AsyncClient(
            headers=self._auth_headers,
            timeout=60.0,
            verify=self.verify_ssl,
            limits=httpx.Limits(
                max_connections=self.max_concurrent_requests,
                max_keepalive_connections=5,
            ),
            follow_redirects=True,
        ) as client:
            tasks = [
                self._fetch_attachments_for_doc(client, semaphore, doc) for doc in docs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                doc_id = (docs[i] or {}).get("id", "?")
                logger.warning(
                    "Failed to fetch attachments for doc {}: {}", doc_id, result
                )
                attachments_map[i] = []
            else:
                attachments_map[i] = result  # type: ignore[assignment]

        return attachments_map

    async def _fetch_attachments_for_doc(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        doc: Optional[dict],
    ) -> list[dict]:
        """Download all attachments for a single document."""
        if not doc:
            return []

        doc_id = doc.get("id", "")
        downloaded: list[dict] = []
        seen_ids: set[str] = set()

        # Attachments from the attachments.list endpoint
        if self.include_attachments:
            listed = await self._list_attachments(client, semaphore, doc_id)
            for att in listed:
                att_id = att.get("id", "")
                if att_id in seen_ids:
                    continue
                seen_ids.add(att_id)
                data = await self._download_attachment_by_id(
                    client, semaphore, att_id, att.get("name", "attachment")
                )
                if data:
                    downloaded.append(data)

        # Inline images embedded in the Markdown body
        if self.download_inline_images:
            text = doc.get("text", "")
            for url in _INLINE_IMAGE_RE.findall(text):
                att_id = self._extract_attachment_id(url)
                if att_id and att_id not in seen_ids:
                    seen_ids.add(att_id)
                    ext = self._ext_from_url(url)
                    data = await self._download_attachment_url(
                        client, semaphore, url, f"{att_id}{ext}", att_id
                    )
                    if data:
                        downloaded.append(data)

        return downloaded

    async def _list_attachments(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        doc_id: str,
    ) -> list[dict]:
        """Call attachments.list for a document."""
        async with semaphore:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/attachments.list",
                    json={"documentId": doc_id, "limit": 100},
                )
                resp.raise_for_status()
                return list(resp.json().get("data", []))
            except Exception as exc:
                logger.debug("Could not list attachments for doc {}: {}", doc_id, exc)
                return []

    async def _download_attachment_by_id(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        att_id: str,
        name: str,
    ) -> Optional[dict]:
        """Download an attachment via the redirect endpoint using its ID."""
        url = f"{self.base_url}/api/attachments.redirect?id={att_id}"
        return await self._download_attachment_url(client, semaphore, url, name, att_id)

    async def _download_attachment_url(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        url: str,
        filename: str,
        att_id: str,
    ) -> Optional[dict]:
        """Download bytes from a URL, respecting the size cap."""
        async with semaphore:
            try:
                resp = await client.get(url)
                resp.raise_for_status()

                content_length = int(resp.headers.get("content-length", 0))
                if content_length > self.max_attachment_size_bytes:
                    logger.warning(
                        "Skipping attachment {} ({:.1f} MB) — exceeds limit",
                        filename,
                        content_length / 1024 / 1024,
                    )
                    return None

                data = resp.content
                if len(data) > self.max_attachment_size_bytes:
                    logger.warning(
                        "Skipping attachment {} ({:.1f} MB) — exceeds limit after download",
                        filename,
                        len(data) / 1024 / 1024,
                    )
                    return None

                mime = resp.headers.get(
                    "content-type", "application/octet-stream"
                ).split(";")[0]
                return {
                    "id": att_id,
                    "filename": filename,
                    "bytes": data,
                    "mimeType": mime,
                }
            except Exception as exc:
                logger.warning("Failed to download attachment {}: {}", filename, exc)
                return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_attachment_id(url: str) -> str:
        """Extract the id query parameter from an attachments.redirect URL."""
        from urllib.parse import parse_qs, urlparse as _up

        parsed = _up(url)
        params = parse_qs(parsed.query)
        ids = params.get("id", [])
        return ids[0] if ids else ""

    @staticmethod
    def _ext_from_url(url: str) -> str:
        """Guess a file extension from a URL path (empty string if none)."""
        path = urlparse(url).path
        last_segment = path.split("/")[-1]
        if "." in last_segment:
            ext = "." + last_segment.rsplit(".", 1)[-1]
            # Skip redirect endpoints — they're not file extensions
            if ext != ".redirect" and len(ext) <= 6:
                return ext
        return ".png"  # Default for Outline inline images

    @staticmethod
    def _raise_for_status(resp: Any) -> None:
        if resp.status_code < 400:
            return
        try:
            message = resp.json().get("message", resp.text[:200])
        except Exception:
            message = resp.text[:200]
        raise OutlineAPIError(
            status_code=resp.status_code,
            message=message,
            url=str(resp.url),
        )
