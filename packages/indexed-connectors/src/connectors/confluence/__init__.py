"""Confluence connectors for indexing pages from Confluence Server/DC and Cloud."""

from .connector import ConfluenceConnector, ConfluenceCloudConnector
from .confluence_document_reader import ConfluenceAPIError
from .confluence_cloud_document_reader import ConfluenceCloudAPIError

__all__ = [
    "ConfluenceConnector",
    "ConfluenceCloudConnector",
    "ConfluenceAPIError",
    "ConfluenceCloudAPIError",
]

# Register Confluence connector config specs (best-effort)
try:
    from indexed_config import ConfigService
    from .schema import ConfluenceConfig, ConfluenceCloudConfig

    _svc = ConfigService.instance()
    _svc.register(ConfluenceConfig, path="connectors.confluence.server")
    _svc.register(ConfluenceCloudConfig, path="connectors.confluence.cloud")
except Exception:
    pass
