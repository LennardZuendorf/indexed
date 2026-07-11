"""Unit tests for connector ``from_manifest`` (foundation/8a).

Each connector rebuilds its reader/converter for an incremental update from the
stored manifest. These tests pin the new logic in isolation: the incremental
date-filter query (including the R6.5 empty-query fix), the in-memory overlay
keys (R3 — never persisted), and the files change-tracking path. The
``from_config`` tail is stubbed for cloud sources (it is covered elsewhere and
needs live credentials).
"""

import fnmatch
import json
import types


from indexed.protocols import ConnectorRun, Manifest


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
    from indexed.connectors.files.connector import FileSystemConnector
    from indexed.connectors.files.files_document_reader import FilesDocumentReader

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


def test_files_from_manifest_propagates_non_default_reader_settings(tmp_path):
    """NON-default reader settings must flow into the rebuilt reader, not default.

    The prior test used only defaults, so it couldn't distinguish "propagated"
    from "defaulted". Here every asserted value differs from the connector's
    default (include ``["*"]``, ``failFast=False``, ``respectGitignore=True``).
    ``includePatterns`` is normalized by ``FileSystemConfig`` (``*.md`` is not
    valid regex, so it becomes ``fnmatch.translate("*.md")``) — assert against
    that same normalization so we test propagation, not the normalizer.
    """
    from indexed.connectors.files.connector import FileSystemConnector
    from indexed.connectors.files.files_document_reader import FilesDocumentReader

    (tmp_path / "doc.md").write_text("hello world")
    manifest = _manifest(
        {
            "type": "localFiles",
            "basePath": str(tmp_path),
            "includePatterns": ["*.md"],
            "failFast": True,
            "respectGitignore": False,
        }
    )

    run = FileSystemConnector.from_manifest(
        manifest, object(), storage_path=str(tmp_path)
    )

    assert isinstance(run.reader, FilesDocumentReader)
    assert run.reader.include_patterns == [fnmatch.translate("*.md")]
    assert run.reader.include_patterns != ["*"]  # not the default
    assert run.reader.fail_fast is True
    assert run.reader._respect_gitignore is False


def test_files_from_manifest_with_change_state_scopes_and_persists(tmp_path):
    """WITH-prior-state branch: deletions + specific_files scoping + post_run save.

    Seed a content-hash state over two files, then modify one and delete the
    other. ``from_manifest`` must return the deleted file in ``deletions``, scope
    the reader to the changed file via ``specific_files``, and expose a
    ``post_run`` hook that rewrites ``state.json`` to the new reality.
    """
    from indexed.connectors.files.connector import FileSystemConnector
    from indexed.connectors.files.files_document_reader import FilesDocumentReader

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.txt").write_text("version one")
    (source / "b.txt").write_text("to be deleted")
    storage = tmp_path / "coll"
    storage.mkdir()

    # Seed a content-hash state snapshot of both files at storage/state.json.
    seed = FileSystemConnector(path=str(source), change_tracking="content_hash")
    seed.save_state(str(storage))
    assert (storage / "state.json").exists()

    # Mutate the tree: a.txt changes, b.txt is deleted.
    (source / "a.txt").write_text("version two — different content")
    (source / "b.txt").unlink()

    manifest = _manifest(
        {
            "type": "localFiles",
            "basePath": str(source),
            "changeTracking": "content_hash",
        }
    )

    run = FileSystemConnector.from_manifest(
        manifest, object(), storage_path=str(storage)
    )

    # Deleted file surfaces as a deletion (relative path == document id).
    assert run.deletions == ["b.txt"]
    # Reader is scoped to the changed file only.
    assert isinstance(run.reader, FilesDocumentReader)
    assert run.reader.specific_files is not None
    assert any(p.endswith("a.txt") for p in run.reader.specific_files)
    assert not any(p.endswith("b.txt") for p in run.reader.specific_files)

    # post_run persists updated state: b.txt gone, a.txt still tracked.
    assert callable(run.post_run)
    run.post_run()
    new_state = json.loads((storage / "state.json").read_text())
    assert "a.txt" in new_state["file_hashes"]
    assert "b.txt" not in new_state["file_hashes"]


# --- jira ----------------------------------------------------------------------


def test_jira_cloud_from_manifest_query_and_overlays(monkeypatch):
    from indexed.connectors.jira.connector import JiraCloudConnector

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
    from indexed.connectors.jira.connector import JiraConnector

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
    from indexed.connectors.confluence.connector import ConfluenceCloudConnector

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
    from indexed.connectors.outline.connector import OutlineConnector

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
            "downloadInlineImages": True,
            "maxConcurrentRequests": 8,
            "maxAttachmentSizeMb": 50,
            "verifySsl": False,
        }
    )

    OutlineConnector.from_manifest(manifest, cs, storage_path="/x")

    # Explicit (non-_OPTIONAL_OVERLAYS) overlays.
    assert cs.overlays["sources.outline.url"] == "https://outline.acme.com"
    assert cs.overlays["sources.outline.include_attachments"] is True
    # Every _OPTIONAL_OVERLAYS entry, mapped camelCase → snake_case.
    assert cs.overlays["sources.outline.collection_ids"] == ["c1"]
    assert cs.overlays["sources.outline.batch_size"] == 25
    assert cs.overlays["sources.outline.ocr_enabled"] is False
    assert cs.overlays["sources.outline.download_inline_images"] is True
    assert cs.overlays["sources.outline.max_concurrent_requests"] == 8
    assert cs.overlays["sources.outline.max_attachment_size_mb"] == 50
    assert cs.overlays["sources.outline.verify_ssl"] is False
    # cutoff replaces the old os.environ side-channel: raw lastModifiedDocumentTime
    assert cs.overlays["sources.outline.modified_since"] == "2026-07-05T09:15:00+00:00"


def test_all_connectors_expose_from_manifest():
    """Every shipped connector gained the from_manifest classmethod."""
    from indexed.connectors.registry import CONNECTOR_REGISTRY

    for connector_cls in CONNECTOR_REGISTRY.values():
        assert hasattr(connector_cls, "from_manifest")
        assert hasattr(connector_cls, "from_config")
