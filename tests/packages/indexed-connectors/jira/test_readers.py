"""Tests for Jira document readers."""
import pytest
from connectors.jira.jira_cloud_document_reader import JiraCloudDocumentReader as CloudReader
from connectors.jira.jira_document_reader import JiraDocumentReader as ServerReader

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
        return {"issues": batch, "total": len(self._issues), "startAt": start, "maxResults": limit}


class FakeJiraServer:
    def __init__(self, url=None, token=None, username=None, password=None, cloud=None, **kwargs):
        self._issues = [
            {"key": "S-1", "fields": {"updated": "2024-02-01T00:00:00.000+0000"}},
            {"key": "S-2", "fields": {"updated": "2024-02-02T00:00:00.000+0000"}},
        ]

    def jql(self, jql, fields=None, start=0, limit=50, expand=None, **kwargs):
        batch = self._issues[start : start + limit] if limit else self._issues[start:]
        return {"issues": batch, "total": len(self._issues), "startAt": start, "maxResults": limit}


def test_cloud_reader_count_and_pagination(monkeypatch):
    # Patch the Jira class in cloud module
    import connectors.jira.jira_cloud_document_reader as cloud_mod

    monkeypatch.setattr(cloud_mod, "Jira", FakeJiraCloud, raising=True)

    reader = CloudReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
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
    import connectors.jira.jira_document_reader as server_mod

    monkeypatch.setattr(server_mod, "Jira", FakeJiraServer, raising=True)

    reader = ServerReader(
        base_url="https://jira.example.com",
        query="project = APP",
        token="pat-token",
        batch_size=1,
    )

    assert reader.get_number_of_documents() == 2

    docs = list(reader.read_all_documents())
    assert len(docs) == 2
    assert docs[0]["key"] == "S-1"