"""Unit tests for connector ``from_manifest`` (foundation/8a).

Each connector rebuilds its reader/converter for an incremental update from the
stored manifest. These tests pin the new logic in isolation: the incremental
date-filter query (including the R6.5 empty-query fix), the in-memory overlay
keys (R3 — never persisted), and the files change-tracking path. The
``from_config`` tail is stubbed for cloud sources (it is covered elsewhere and
needs live credentials).
"""

import types


from protocols import ConnectorRun, Manifest


class _FakeConfigService:
    """Records set_overlay calls; stands in for ConfigService."""

    def __init__(self) -> None:
        self.overlays: dict = {}

    def set_overlay(self, dot_path: str, value) -> None:
        self.overlays[dot_path] = value


def _manifest(reader: dict) -> Manifest:
    return Manifest.from_disk(
        {
            "collectionName": "c",
            "createdTime": "2026-07-01T00:00:00+00:00",
            "updatedTime": "2026-07-07T00:00:00+00:00",
            "lastModifiedDocumentTime": "2026-07-05T09:15:00+00:00",
            "numberOfDocuments": 3,
            "numberOfChunks": 30,
            "reader": reader,
            "indexers": [{"name": "faiss-flat-l2"}],
        }
    )


# cutoff = lastModifiedDocumentTime - 1 day = 2026-07-04
_CUTOFF = "2026-07-04"


# --- files ---------------------------------------------------------------------


def test_files_from_manifest_builds_reader_and_hooks(tmp_path):
    from connectors.files.connector import FileSystemConnector
    from connectors.files.files_document_reader import FilesDocumentReader

    (tmp_path / "doc.md").write_text("hello world")
    manifest = _manifest(
        {
            "type": "localFiles",
            "basePath": str(tmp_path),
            "includePatterns": ["*"],
            "failFast": False,
            "respectGitignore": True,
        }
    )

    run = FileSystemConnector.from_manifest(
        manifest, object(), storage_path=str(tmp_path)
    )

    assert isinstance(run, ConnectorRun)
    assert isinstance(run.reader, FilesDocumentReader)
    assert run.converter is not None
    assert run.deletions == []  # no prior state.json → nothing deleted
    assert callable(run.post_run)


# --- jira ----------------------------------------------------------------------


def test_jira_cloud_from_manifest_query_and_overlays(monkeypatch):
    from connectors.jira.connector import JiraCloudConnector

    sentinel = types.SimpleNamespace(reader="R", converter="C")
    monkeypatch.setattr(
        JiraCloudConnector,
        "from_config",
        classmethod(lambda cls, cs: sentinel),
    )
    cs = _FakeConfigService()
    manifest = _manifest(
        {
            "type": "jiraCloud",
            "baseUrl": "https://acme.atlassian.net",
            "query": "project = ENG",
        }
    )

    run = JiraCloudConnector.from_manifest(manifest, cs, storage_path="/x")

    assert run.reader == "R" and run.converter == "C"
    assert run.deletions == [] and run.post_run is None
    assert cs.overlays["sources.jira.url"] == "https://acme.atlassian.net"
    query = cs.overlays["sources.jira.query"]
    assert (
        query == f'project = ENG AND (created >= "{_CUTOFF}" OR updated >= "{_CUTOFF}")'
    )


def test_jira_from_manifest_empty_query_has_no_leading_and(monkeypatch):
    """R6.5: an empty stored query must not yield leading-AND (invalid) JQL."""
    from connectors.jira.connector import JiraConnector

    monkeypatch.setattr(
        JiraConnector,
        "from_config",
        classmethod(lambda cls, cs: types.SimpleNamespace(reader="R", converter="C")),
    )
    cs = _FakeConfigService()
    manifest = _manifest(
        {"type": "jira", "baseUrl": "https://jira.example.com", "query": ""}
    )

    JiraConnector.from_manifest(manifest, cs, storage_path="/x")

    query = cs.overlays["sources.jira.query"]
    assert not query.lstrip().startswith("AND")
    assert query == f'(created >= "{_CUTOFF}" OR updated >= "{_CUTOFF}")'


# --- confluence ----------------------------------------------------------------


def test_confluence_cloud_from_manifest_query_and_overlays(monkeypatch):
    from connectors.confluence.connector import ConfluenceCloudConnector

    monkeypatch.setattr(
        ConfluenceCloudConnector,
        "from_config",
        classmethod(lambda cls, cs: types.SimpleNamespace(reader="R", converter="C")),
    )
    cs = _FakeConfigService()
    manifest = _manifest(
        {
            "type": "confluenceCloud",
            "baseUrl": "https://acme.atlassian.net/wiki",
            "query": "space = DOCS",
            "readAllComments": False,
        }
    )

    ConfluenceCloudConnector.from_manifest(manifest, cs, storage_path="/x")

    query = cs.overlays["sources.confluence.query"]
    assert (
        query
        == f'space = DOCS AND (created >= "{_CUTOFF}" OR lastModified >= "{_CUTOFF}")'
    )
    assert cs.overlays["sources.confluence.read_all_comments"] is False


# --- outline -------------------------------------------------------------------


def test_outline_from_manifest_overlays_and_cutoff(monkeypatch):
    from connectors.outline.connector import OutlineConnector

    monkeypatch.setattr(
        OutlineConnector,
        "from_config",
        classmethod(lambda cls, cs: types.SimpleNamespace(reader="R", converter="C")),
    )
    cs = _FakeConfigService()
    manifest = _manifest(
        {
            "type": "outline",
            "baseUrl": "https://outline.acme.com",
            "collectionIds": ["c1"],
            "batchSize": 25,
            "includeAttachments": True,
            "ocrEnabled": False,
        }
    )

    OutlineConnector.from_manifest(manifest, cs, storage_path="/x")

    assert cs.overlays["sources.outline.url"] == "https://outline.acme.com"
    assert cs.overlays["sources.outline.collection_ids"] == ["c1"]
    assert cs.overlays["sources.outline.batch_size"] == 25
    assert cs.overlays["sources.outline.ocr_enabled"] is False
    # cutoff replaces the old os.environ side-channel: raw lastModifiedDocumentTime
    assert cs.overlays["sources.outline.modified_since"] == "2026-07-05T09:15:00+00:00"


def test_all_connectors_expose_from_manifest():
    """Every shipped connector gained the from_manifest classmethod."""
    from connectors.registry import CONNECTOR_REGISTRY

    for connector_cls in CONNECTOR_REGISTRY.values():
        assert hasattr(connector_cls, "from_manifest")
        assert hasattr(connector_cls, "from_config")
