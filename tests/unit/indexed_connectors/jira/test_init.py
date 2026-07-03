"""Registry membership and public export tests for the Jira connector."""

from connectors.jira import JiraConnector, JiraCloudConnector


def test_jira_init_imports():
    """Test that imports work correctly."""
    assert JiraConnector is not None
    assert JiraCloudConnector is not None


def test_jira_in_connector_registry() -> None:
    from connectors.registry import CONNECTOR_REGISTRY

    assert "jira" in CONNECTOR_REGISTRY
    assert "jiraCloud" in CONNECTOR_REGISTRY


def test_jira_in_config_registry() -> None:
    from connectors.registry import CONFIG_REGISTRY

    assert "jira" in CONFIG_REGISTRY
    assert "jiraCloud" in CONFIG_REGISTRY


def test_jira_in_namespace_registry() -> None:
    from connectors.registry import NAMESPACE_REGISTRY

    assert NAMESPACE_REGISTRY["jira"] == "sources.jira"
    assert NAMESPACE_REGISTRY["jiraCloud"] == "sources.jira"


def test_get_connector_class_jira() -> None:
    from connectors.registry import get_connector_class
    from connectors.jira.connector import JiraConnector, JiraCloudConnector

    assert get_connector_class("jira") is JiraConnector
    assert get_connector_class("jiraCloud") is JiraCloudConnector


def test_get_config_class_jira() -> None:
    from connectors.registry import get_config_class
    from connectors.jira.schema import JiraConfig, JiraCloudConfig

    assert get_config_class("jira") is JiraConfig
    assert get_config_class("jiraCloud") is JiraCloudConfig
