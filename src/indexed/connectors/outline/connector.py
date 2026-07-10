"""Outline Wiki connector for Cloud and self-hosted deployments.

A single connector class handles both Outline Cloud (https://app.getoutline.com)
and self-hosted Outline instances — the API is identical across both; only the
base URL differs.
"""

from typing import Any, ClassVar

from indexed.protocols import ConnectorMetadata, ConnectorRun, Manifest

from .outline_document_converter import OutlineDocumentConverter
from .outline_document_reader import OutlineDocumentReader
from .schema import OUTLINE_CLOUD_URL, OutlineConfig

# Optional Outline reader settings carried forward on an incremental update:
# (manifest camelCase key, config snake_key). Only applied when present in the
# stored manifest, so an unset key keeps the connector's own default.
_OPTIONAL_OVERLAYS = (
    ("collectionIds", "collection_ids"),
    ("batchSize", "batch_size"),
    ("ocrEnabled", "ocr_enabled"),
    ("downloadInlineImages", "download_inline_images"),
    ("maxConcurrentRequests", "max_concurrent_requests"),
    ("maxAttachmentSizeMb", "max_attachment_size_mb"),
    ("verifySsl", "verify_ssl"),
)


class OutlineConnector:
    """Connector for Outline Wiki (Cloud or self-hosted).

    Indexes Outline documents and optionally their attachments/inline images
    using the Outline REST API authenticated with an API key.

    Works identically against Outline Cloud and self-hosted deployments — the
    only difference is the ``url`` field in the configuration.

    Examples:
        >>> # Outline Cloud (default URL)
        >>> connector = OutlineConnector(OutlineConfig(
        ...     api_token="ol_api_...",
        ... ))
        >>> # Self-hosted
        >>> connector = OutlineConnector(OutlineConfig(
        ...     url="https://wiki.acme.internal",
        ...     api_token="ol_api_...",
        ... ))
    """

    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="outline",
        display_name="Outline Wiki (Cloud or self-hosted)",
        description="Index Outline Wiki documents and attachments via API key",
        config_class=OutlineConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create outline --collection wiki",
    )

    def __init__(self, config: OutlineConfig) -> None:
        self._config = config

        api_token = config.get_api_token()

        self._reader = OutlineDocumentReader(
            base_url=config.url,
            api_token=api_token,
            collection_ids=config.collection_ids,
            batch_size=config.batch_size,
            max_concurrent_requests=config.max_concurrent_requests,
            include_attachments=config.include_attachments,
            download_inline_images=config.download_inline_images,
            ocr_enabled=config.ocr_enabled,
            max_attachment_size_mb=config.max_attachment_size_mb,
            verify_ssl=config.verify_ssl,
            modified_since=config.modified_since,
        )
        self._converter = OutlineDocumentConverter(
            max_chunk_tokens=config.max_chunk_tokens,
            ocr=config.ocr_enabled,
            include_attachments=config.include_attachments,
        )

    @property
    def reader(self) -> OutlineDocumentReader:
        return self._reader

    @property
    def converter(self) -> OutlineDocumentConverter:
        return self._converter

    @property
    def connector_type(self) -> str:
        return "outline"

    def __repr__(self) -> str:
        deployment = "Cloud" if self._config.is_cloud() else "self-hosted"
        return f"OutlineConnector(url='{self._config.url}', deployment='{deployment}')"

    # ------------------------------------------------------------------
    # Configuration integration
    # ------------------------------------------------------------------

    @classmethod
    def config_spec(cls) -> dict:
        return {
            "url": {
                "type": "str",
                "required": False,
                "secret": False,
                "default": OUTLINE_CLOUD_URL,
                "description": "Outline base URL (Cloud default or self-hosted domain)",
            },
            "api_token": {
                "type": "str",
                "required": True,
                "secret": True,
                "default": "OUTLINE_API_TOKEN",
                "description": "Env var containing the Outline API token",
            },
            "collection_ids": {
                "type": "list[str]",
                "required": False,
                "secret": False,
                "default": None,
                "description": "Restrict to specific collection IDs (None = all)",
            },
            "include_attachments": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": True,
                "description": "Download and OCR attachments and inline images",
            },
        }

    @classmethod
    def from_config(cls, config_service: object) -> "OutlineConnector":
        """Create an OutlineConnector from a ConfigService instance."""
        config_service.register(OutlineConfig, path="sources.outline")  # type: ignore[attr-defined]
        provider = config_service.bind()  # type: ignore[attr-defined]
        cfg = provider.get(OutlineConfig)
        return cls(cfg)

    @classmethod
    def from_manifest(
        cls, manifest: Manifest, config_service: Any, *, storage_path: str
    ) -> ConnectorRun:
        """Rebuild the Outline connector for an incremental update.

        Carries the stored reader settings forward as in-memory overlays (R3)
        and sets the incremental cutoff via ``modified_since`` — replacing the
        previous ``os.environ`` side-channel — from the manifest's
        ``lastModifiedDocumentTime`` (the raw value, matching prior behavior).
        """
        rd = manifest.reader.model_dump(by_alias=True)
        ns = "sources.outline"
        overlay = config_service.set_overlay

        overlay(f"{ns}.url", rd["baseUrl"])
        overlay(f"{ns}.include_attachments", rd.get("includeAttachments", True))
        for manifest_key, config_key in _OPTIONAL_OVERLAYS:
            if rd.get(manifest_key) is not None:
                overlay(f"{ns}.{config_key}", rd[manifest_key])
        overlay(f"{ns}.modified_since", manifest.last_modified_document_time)

        connector = cls.from_config(config_service)
        return ConnectorRun(connector.reader, connector.converter, [], None)


__all__ = ["OutlineConnector"]
