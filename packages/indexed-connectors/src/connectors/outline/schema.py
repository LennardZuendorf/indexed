"""Configuration schema for the Outline Wiki connector."""

import os
from typing import Optional

from pydantic import BaseModel, Field, field_validator


OUTLINE_CLOUD_URL = "https://app.getoutline.com"


class OutlineConfig(BaseModel):
    """Configuration for Outline Wiki (Cloud or self-hosted)."""

    url: str = Field(
        default=OUTLINE_CLOUD_URL,
        description="Outline base URL — use https://app.getoutline.com for Cloud, or your own domain for self-hosted",
    )
    api_token: Optional[str] = Field(
        None, description="Outline API token (env: OUTLINE_API_TOKEN)"
    )
    collection_ids: Optional[list[str]] = Field(
        None,
        description="Restrict indexing to specific collection IDs. None = index all collections.",
    )
    include_attachments: bool = Field(
        True, description="Download and parse file attachments and inline images"
    )
    download_inline_images: bool = Field(
        True,
        description="Extract and download images referenced inline in document Markdown",
    )
    ocr_enabled: bool = Field(
        True, description="Enable OCR for image attachments via ParsingModule"
    )
    max_chunk_tokens: int = Field(
        default=512, ge=64, le=2048, description="Max tokens per chunk"
    )
    max_attachment_size_mb: int = Field(
        default=10, ge=1, le=100, description="Max attachment size in MB to download"
    )
    batch_size: int = Field(
        default=50, ge=1, le=250, description="Documents per API page request"
    )
    max_concurrent_requests: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Max concurrent HTTP requests for body/attachment fetching",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify TLS certificates. Set False for self-hosted instances with self-signed CAs.",
    )

    @field_validator("url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return str(v).rstrip("/")

    def get_api_token(self) -> str:
        """Return the API token from config or OUTLINE_API_TOKEN env var."""
        token = self.api_token or os.getenv("OUTLINE_API_TOKEN")
        if not token:
            raise ValueError("OUTLINE_API_TOKEN not set in config or environment")
        return token

    def is_cloud(self) -> bool:
        """Return True if this config targets Outline Cloud."""
        return self.url == OUTLINE_CLOUD_URL


__all__ = ["OutlineConfig", "OUTLINE_CLOUD_URL"]
