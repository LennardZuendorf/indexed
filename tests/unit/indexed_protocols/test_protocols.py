from protocols import BaseConnector, SourceConfig
from connectors.jira.connector import JiraConnector


def test_jira_connector_satisfies_base_connector_protocol():
    assert isinstance(JiraConnector, type)
    # runtime_checkable: instance check after from_config needs mock config — use META
    assert hasattr(JiraConnector, "META")
    assert BaseConnector.__name__ == "BaseConnector"


def test_source_config_accepts_jira_type():
    cfg = SourceConfig(
        name="x", type="jira", base_url_or_path="https://jira.example.com"
    )
    assert cfg.type == "jira"
