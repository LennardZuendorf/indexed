from unittest.mock import MagicMock

import pytest

from indexed.connectors.github.connector import GitHubConnector
from indexed.connectors.github.schema import GitHubConfig
from indexed.connectors.github.github_document_converter import GitHubDocumentConverter
from indexed.connectors.github.github_graphql_reader import GitHubGraphQLReader


def test_connector_type():
    connector = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert connector.connector_type == "github"


def test_reader_and_converter_exposed():
    connector = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert isinstance(connector.reader, GitHubGraphQLReader)
    assert isinstance(connector.converter, GitHubDocumentConverter)


def test_repr_reports_cloud_vs_enterprise():
    cloud = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert "Cloud" in repr(cloud)
    enterprise = GitHubConnector(
        GitHubConfig(repos=["octo/hello"], token="ghp_x", host="github.example.com")
    )
    assert "Enterprise" in repr(enterprise)


def test_requires_repos_or_project():
    with pytest.raises(Exception, match="repos.*project|project.*repos"):
        GitHubConnector(GitHubConfig(repos=[], project=None, token="ghp_x"))


def test_meta_identity():
    assert GitHubConnector.META.name == "github"
    assert GitHubConnector.META.config_class is GitHubConfig


def test_config_spec_has_expected_fields():
    spec = GitHubConnector.config_spec()
    assert set(["repos", "project", "host", "token", "state"]).issubset(spec.keys())
    assert spec["token"]["secret"] is True


def test_from_config_registers_and_binds():
    config_service = MagicMock()
    provider = MagicMock()
    provider.get.return_value = GitHubConfig(repos=["octo/hello"], token="ghp_x")
    config_service.bind.return_value = provider

    connector = GitHubConnector.from_config(config_service)

    config_service.register.assert_called_once_with(GitHubConfig, path="sources.github")
    assert connector.connector_type == "github"


def test_base_connector_protocol_conformance():
    from indexed.protocols import BaseConnector

    connector = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert isinstance(connector, BaseConnector)
