"""Async Outline Wiki document reader.

Sequential collection/document listing with concurrent body + attachment
fetching in windows of 100, mirroring AsyncConfluenceCloudDocumentReader.
"""

from __future__ import annotations

import asyncio
import base64
import re
from datetime import datetime
from typing import Any, Iterator, Optional
from urllib.parse import parse_qs, urlparse

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
        modified_since: ISO timestamp cutoff for incremental updates. When set,
            only documents with updatedAt >= this value are listed (via sorted
            early-stop). Internal — set by the update factory, not persisted.
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
        ocr_enabled: bool = True,
        max_attachment_size_mb: int = 10,
        number_of_retries: int = 3,
        retry_delay: float = 1.0,
        verify_ssl: bool = True,
        modified_since: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.collection_ids = collection_ids
        self.batch_size = batch_size
        self.max_concurrent_requests = max_concurrent_requests
        self.include_attachments = include_attachments
        self.download_inline_images = download_inline_images
        # Stored for manifest roundtrip only; OCR runs in OutlineDocumentConverter.
        self.ocr_enabled = ocr_enabled
        self.max_attachment_size_bytes = max_attachment_size_mb * 1024 * 1024
        self.number_of_retries = number_of_retries
        self.retry_delay = retry_delay
        self.verify_ssl = verify_ssl
        if not verify_ssl:
            logger.warning(
                "Outline: TLS certificate verification is DISABLED (verify_ssl=False). "
                "Your API token may be exposed to a man-in-the-middle. Only use this for "
                "trusted self-hosted instances with self-signed certificates."
            )
        self._modified_since_cutoff = self._parse_iso_datetime(modified_since)
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
                "attachments": [{"filename": str, "bytes": str, "mimeType": str, "id": str}]
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
        if self._modified_since_cutoff is not None:
            return sum(1 for _ in self._iter_document_stubs())

        total = 0
        for cid in self._get_collection_ids_sync():
            resp = self._post_with_retry(
                f"{self.base_url}/api/documents.list",
                {
                    "collectionId": cid,
                    "status": "published",
                    "limit": 1,
                    "offset": 0,
                },
            )
            total += resp.json().get("pagination", {}).get("total", 0)
        return total

    def get_reader_details(self) -> dict:
        return {
            "type": "outline",
            "baseUrl": self.base_url,
            "collectionIds": self.collection_ids,
            "batchSize": self.batch_size,
            "includeAttachments": self.include_attachments,
            "downloadInlineImages": self.download_inline_images,
            "maxConcurrentRequests": self.max_concurrent_requests,
            "maxAttachmentSizeMb": self.max_attachment_size_bytes // (1024 * 1024),
            "verifySsl": self.verify_ssl,
            "ocrEnabled": self.ocr_enabled,
        }

    # ------------------------------------------------------------------
    # Sequential listing
    # ------------------------------------------------------------------

    def _iter_document_stubs(self) -> Iterator[dict]:
        """Yield minimal document stubs (id, title, updatedAt, etc.) for all collections."""
        for collection_id in self._get_collection_ids_sync():
            offset = 0
            logger.debug("Listing documents in collection {}", collection_id)
            while True:
                resp = self._post_with_retry(
                    f"{self.base_url}/api/documents.list",
                    self._documents_list_payload(collection_id, offset),
                )
                result = resp.json()
                docs = result.get("data", [])
                pagination = result.get("pagination", {})
                total = pagination.get("total", 0)

                stop_collection = False
                for doc in docs:
                    if self._is_older_than_cutoff(doc):
                        stop_collection = True
                        break
                    yield doc

                if stop_collection:
                    break

                offset += len(docs)
                if not docs or offset >= total:
                    break

    def _get_collection_ids_sync(self) -> list[str]:
        """Return collection IDs to index — from config or by listing all."""
        if self.collection_ids is not None:
            return self.collection_ids

        ids: list[str] = []
        offset = 0
        while True:
            resp = self._post_with_retry(
                f"{self.base_url}/api/collections.list",
                {"limit": 100, "offset": offset},
            )
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
        if self.include_attachments:
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
        if self.include_attachments and self.download_inline_images:
            text = doc.get("text", "")
            base_origin = urlparse(self.base_url)
            for url in _INLINE_IMAGE_RE.findall(text):
                parsed_url = urlparse(url)
                if (parsed_url.scheme, parsed_url.netloc) != (
                    base_origin.scheme,
                    base_origin.netloc,
                ):
                    logger.warning(
                        "Skipping cross-origin inline attachment URL for doc {}: {}",
                        doc_id,
                        url,
                    )
                    continue
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
            from .._url_guard import warn_if_off_origin

            if not warn_if_off_origin(url, self.base_url):
                return None

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
                    "bytes": base64.b64encode(data).decode("ascii"),
                    "mimeType": mime,
                }
            except Exception as exc:
                logger.warning("Failed to download attachment {}: {}", filename, exc)
                return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _documents_list_payload(self, collection_id: str, offset: int) -> dict:
        """Build the documents.list request body for a collection page."""
        return {
            "collectionId": collection_id,
            "status": "published",
            "limit": self.batch_size,
            "offset": offset,
            "sort": "updatedAt",
            "direction": "DESC",
        }

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> Optional[datetime]:
        if not value:
            return None
        normalized = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    def _is_older_than_cutoff(self, doc: dict) -> bool:
        """Return True when a stub is older than the incremental update cutoff."""
        if self._modified_since_cutoff is None:
            return False
        doc_updated = self._parse_iso_datetime(doc.get("updatedAt"))
        if doc_updated is None:
            return False
        return doc_updated < self._modified_since_cutoff

    @staticmethod
    def _extract_attachment_id(url: str) -> str:
        """Extract the id query parameter from an attachments.redirect URL."""
        parsed = urlparse(url)
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

    def _post_with_retry(self, url: str, json: dict) -> Any:
        """POST with timeout=(5,30) and retry on transient/rate-limit errors."""
        import time

        import requests  # type: ignore[import-untyped]

        for attempt in range(self.number_of_retries):
            try:
                resp = requests.post(
                    url,
                    headers=self._auth_headers,
                    json=json,
                    verify=self.verify_ssl,
                    timeout=(5, 30),
                )
                self._raise_for_status(resp)
                return resp
            except OutlineAPIError as exc:
                if exc.status_code not in (429, 500, 502, 503, 504):
                    raise
                if attempt == self.number_of_retries - 1:
                    raise
                logger.debug(
                    "Retry {}/{} after HTTP {}: {}",
                    attempt + 1,
                    self.number_of_retries,
                    exc.status_code,
                    exc,
                )
                time.sleep(self.retry_delay * (2**attempt))
            except Exception as exc:
                if attempt == self.number_of_retries - 1:
                    raise
                logger.debug(
                    "Retry {}/{}: {}", attempt + 1, self.number_of_retries, exc
                )
                time.sleep(self.retry_delay * (2**attempt))
        raise RuntimeError("unreachable")  # pragma: no cover

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
