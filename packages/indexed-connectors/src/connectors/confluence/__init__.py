"""Confluence connectors for indexing pages from Confluence Server/DC and Cloud."""

from .connector import ConfluenceConnector, ConfluenceCloudConnector

__all__ = ["ConfluenceConnector", "ConfluenceCloudConnector"]

# Register Confluence connector config specs (best-effort)
try:
    from indexed_config import ConfigService
    from .schema import ConfluenceConfig, ConfluenceCloudConfig

    _svc = ConfigService.instance()
    _svc.register(ConfluenceConfig, path="connectors.confluence")
    _svc.register(ConfluenceCloudConfig, path="connectors.confluence_cloud")
except Exception:
    pass
