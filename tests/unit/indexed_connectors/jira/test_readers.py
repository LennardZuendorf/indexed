"""Tests for Jira document readers."""

import pytest
from connectors.jira.unified_jira_document_reader import (
    UnifiedJiraDocumentReader,
    JiraAuthType,
)

pytestmark = pytest.mark.connectors  # Mark all tests in this file as connector tests


class FakeJiraCloud:
    def __init__(self, url=None, username=None, password=None, cloud=None, **kwargs):
        self._issues = [
            {"key": "ISSUE-1", "fields": {"updated": "2024-01-01T00:00:00.000+0000"}},
            {"key": "ISSUE-2", "fields": {"updated": "2024-01-02T00:00:00.000+0000"}},
            {"key": "ISSUE-3", "fields": {"updated": "2024-01-03T00:00:00.000+0000"}},
        ]

    def jql(self, jql, fields=None, start=0, limit=50, expand=None, **kwargs):
        batch = self._issues[start : start + limit] if limit else self._issues[start:]
        return {
            "issues": batch,
            "total": len(self._issues),
            "startAt": start,
            "maxResults": limit,
        }


class FakeJiraServer:
    def __init__(
        self, url=None, token=None, username=None, password=None, cloud=None, **kwargs
    ):
        self._issues = [
            {"key": "S-1", "fields": {"updated": "2024-02-01T00:00:00.000+0000"}},
            {"key": "S-2", "fields": {"updated": "2024-02-02T00:00:00.000+0000"}},
        ]

    def jql(self, jql, fields=None, start=0, limit=50, expand=None, **kwargs):
        batch = self._issues[start : start + limit] if limit else self._issues[start:]
        return {
            "issues": batch,
            "total": len(self._issues),
            "startAt": start,
            "maxResults": limit,
        }


def test_cloud_reader_count_and_pagination(monkeypatch):
    """Test cloud reader document counting and pagination."""
    # Patch the Jira class in the unified reader module
    import connectors.jira.unified_jira_document_reader as unified_mod

    monkeypatch.setattr(unified_mod, "Jira", FakeJiraCloud, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
        auth_type=JiraAuthType.CLOUD,
        email="x@acme.com",
        api_token="token",
        batch_size=2,
    )

    assert reader.get_number_of_documents() == 3

    docs = list(reader.read_all_documents())
    # We yielded raw issue objects, ensure full set arrived
    assert len(docs) == 3
    assert docs[0]["key"] == "ISSUE-1"
    assert docs[-1]["key"] == "ISSUE-3"


def test_server_reader_count_and_pagination(monkeypatch):
    """Test server reader document counting and pagination."""
    import connectors.jira.unified_jira_document_reader as unified_mod

    monkeypatch.setattr(unified_mod, "Jira", FakeJiraServer, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = APP",
        auth_type=JiraAuthType.SERVER_TOKEN,
        token="pat-token",
        batch_size=1,
    )

    assert reader.get_number_of_documents() == 2

    docs = list(reader.read_all_documents())
    assert len(docs) == 2
    assert docs[0]["key"] == "S-1"


def test_reader_validation_cloud_requires_email_and_token():
    """Test cloud auth validation."""
    with pytest.raises(
        ValueError, match="Cloud authentication requires both 'email' and 'api_token'"
    ):
        UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            # Missing email and api_token
        )


def test_reader_validation_server_token_requires_token():
    """Test server token auth validation."""
    with pytest.raises(ValueError, match="Token authentication requires 'token'"):
        UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",
            query="project = TEST",
            auth_type=JiraAuthType.SERVER_TOKEN,
            # Missing token
        )


def test_reader_validation_server_creds_requires_login_password():
    """Test server credentials auth validation."""
    with pytest.raises(
        ValueError,
        match="Credential authentication requires both 'login' and 'password'",
    ):
        UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",
            query="project = TEST",
            auth_type=JiraAuthType.SERVER_CREDENTIALS,
            # Missing login and password
        )


def test_reader_url_validation_cloud():
    """Test cloud URL validation."""
    with pytest.raises(ValueError, match="Cloud URLs must end with .atlassian.net"):
        UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",  # Wrong URL for cloud
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="token",
        )


def test_reader_url_validation_server():
    """Test server URL validation."""
    with pytest.raises(
        ValueError, match="Server/DC URLs should not end with .atlassian.net"
    ):
        UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",  # Wrong URL for server
            query="project = TEST",
            auth_type=JiraAuthType.SERVER_TOKEN,
            token="token",
        )


def test_reader_details(monkeypatch):
    """Test get_reader_details returns correct information."""
    import connectors.jira.unified_jira_document_reader as unified_mod

    monkeypatch.setattr(unified_mod, "Jira", FakeJiraCloud, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
        auth_type=JiraAuthType.CLOUD,
        email="x@acme.com",
        api_token="token",
        batch_size=100,
    )

    details = reader.get_reader_details()

    assert details["type"] == "jiraCloud"
    assert details["baseUrl"] == "https://acme.atlassian.net"
    assert details["query"] == "project = TEST"
    assert details["batchSize"] == 100
