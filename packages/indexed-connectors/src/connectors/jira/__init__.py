"""Jira connectors package."""

from .connector import JiraConnector, JiraCloudConnector

__all__ = ["JiraConnector", "JiraCloudConnector"]

# Register Jira connector config specs (best-effort)
try:
    from indexed_config import ConfigService
    from .schema import JiraConfig, JiraCloudConfig

    _svc = ConfigService.instance()
    _svc.register(JiraConfig, path="connectors.jira")
    _svc.register(JiraCloudConfig, path="connectors.jira_cloud")
except Exception:
    pass
