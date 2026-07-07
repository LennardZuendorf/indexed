"""Session-wide fixtures for isolated configuration.

This autouse fixture redirects global/workspace config paths used by
ConfigService so that tests cannot interact with real user or repository
configuration files. All tests run against temporary, empty TOML files
created inside a sandbox dir.

It also exposes the shared behavior-net scaffolding used by the
``tests/characterization`` suite (foundation/1): an isolated local workspace,
a real files corpus with a known "needle" document, and a collection builder
that drives the *real* engine (``DocumentCollectionCreator`` via
``create_collection_creator``) so tests exercise real FAISS + embeddings.
Stubbed-HTTP fixtures for the cloud connectors (jira/confluence/outline) live
alongside them and stub the network at the ``read_documents`` boundary only.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch

from indexed_config import ConfigService

# Canonical default indexer name (FAISS flat + all-MiniLM-L6-v2), matching the
# on-disk manifest the CLI produces.
DEFAULT_INDEXER_NAME = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


@pytest.fixture(scope="session", autouse=True)
def isolate_config_paths(tmp_path_factory: pytest.TempPathFactory):
    """Redirect config helper paths for the entire test session without using the
    function-scoped ``monkeypatch`` fixture (avoids ScopeMismatch errors).
    """

    mp = MonkeyPatch()

    sandbox_root = tmp_path_factory.mktemp("indexed_config_sandbox")

    # Create a fake HOME inside sandbox and point Path.home() to it
    sandbox_home = sandbox_root / "home"
    sandbox_home.mkdir(parents=True, exist_ok=True)

    # Create sandbox global root at ~/.indexed
    global_root = sandbox_home / ".indexed"
    global_root.mkdir(parents=True, exist_ok=True)
    (global_root / "config.toml").touch()

    # Also prepare a local root template (not overriding default behavior)
    local_template = sandbox_root / "local"
    local_template.mkdir(parents=True, exist_ok=True)
    (local_template / "config.toml").touch()

    # Patch Path.home to return sandbox_home so code using Path.home() is isolated
    mp.setattr(Path, "home", lambda: sandbox_home)

    # Reset ConfigService singleton for clean test state
    ConfigService.reset()

    yield  # run the test session

    # Teardown: undo monkeypatches and reset ConfigService singleton
    mp.undo()
    ConfigService.reset()


@pytest.fixture(autouse=True)
def reset_config_service():
    """Ensure ConfigService cache is cleared before and after each test."""
    ConfigService.reset()
    yield
    ConfigService.reset()


@pytest.fixture(autouse=True)
def reset_simple_output_state():
    """Clear the process-global ``simple_output`` flag/cache around every test.

    ``indexed.utils.simple_output`` keeps a module-level ``_simple_output_flag``
    and ``_resolved_cache``; a test that toggles simple-output mode can otherwise
    leak that state into a later test, making CLI-output assertions order-dependent.
    Reset before and after each test so every test starts from the unset default.
    Imported lazily so non-app tests don't couple to the ``indexed`` package.
    """
    try:
        from indexed.utils.simple_output import reset_simple_output
    except Exception:
        yield
        return
    reset_simple_output()
    yield
    reset_simple_output()


@pytest.fixture(autouse=True)
def _reset_app_logging_state():
    """Reset loguru sinks + the app's logging-configured flag between tests.

    The CLI configures loguru exactly once per process, guarded by the
    module-global ``utils.logger._LOGGING_CONFIGURED``. Within a single test
    process, many ``CliRunner`` invocations share that global, so a command
    that installs a stdout log sink (e.g. ``create``) leaks it into a later
    command, whose diagnostic logs then corrupt stdout — an inspect-error line
    gets prepended to ``--simple-output`` JSON, making output assertions
    order-dependent. In production each command is its own process, so this only
    bites tests. Reset after each test so every test starts from unconfigured
    logging. Imported lazily so non-app tests don't couple to these packages.
    """
    yield
    try:
        from loguru import logger as _loguru_logger

        import utils.logger as _ulog

        _loguru_logger.remove()
        _ulog._LOGGING_CONFIGURED = False
        _ulog._CURRENT_LOG_LEVEL = None
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Behavior-net scaffolding (foundation/1)
# ---------------------------------------------------------------------------


def model_available() -> bool:
    """True when the default embedding model is cached locally.

    The behavior net runs real embeddings; when the model is not cached the
    lifecycle tests skip rather than attempt a network download mid-suite.
    """
    try:
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        return is_model_cached("all-MiniLM-L6-v2")
    except Exception:
        return False


@pytest.fixture
def local_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An isolated ``./.indexed`` local workspace rooted at ``tmp_path``.

    Chdirs into ``tmp_path`` and materializes the local storage dirs, so every
    collection built or CLI command run under this fixture lands in the temp
    tree — never the real ``~/.indexed``. Returns a namespace with ``root``,
    ``local_root`` and ``collections_dir``.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TQDM_DISABLE", "1")
    from indexed_config import ensure_storage_dirs, get_local_root

    ConfigService.reset()
    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)
    collections_dir = local_root / "data" / "collections"
    return SimpleNamespace(
        root=tmp_path,
        local_root=local_root,
        collections_dir=collections_dir,
    )


@pytest.fixture
def files_corpus(tmp_path: Path) -> Path:
    """A small real files corpus with a known "needle" document.

    The needle carries a distinctive phrase used by the files lifecycle test to
    assert a *known* document is the top search hit — not merely "no error".
    """
    src = tmp_path / "corpus"
    src.mkdir()
    (src / "alpha.txt").write_text(
        "Semantic search finds documents by meaning rather than exact keywords.\n"
    )
    (src / "beta.txt").write_text(
        "Vector indexing and embeddings power modern document retrieval systems.\n"
    )
    (src / "needle.txt").write_text(
        "The penguin migration survey recorded record numbers along the "
        "Antarctic coastline this austral summer.\n"
    )
    return src


@pytest.fixture
def build_collection():
    """Return a helper that builds a real, searchable collection.

    Drives the same factory the CLI uses
    (``create_collection_creator`` → ``DocumentCollectionCreator.run``), so the
    on-disk layout (FAISS index, mappings, documents, manifest) is produced the
    way production produces it. Accepts any ``reader``/``converter`` pair, so
    both the files connector and stubbed cloud connectors flow through it with
    real FAISS + embeddings.
    """

    def _build(
        collections_dir: Path,
        name: str,
        reader,
        converter,
        *,
        indexer: str = DEFAULT_INDEXER_NAME,
        use_cache: bool = False,
    ) -> Path:
        from core.v1.engine.factories.create_collection_factory import (
            create_collection_creator,
        )

        creator = create_collection_creator(
            collection_name=name,
            indexers=[indexer],
            document_reader=reader,
            document_converter=converter,
            use_cache=use_cache,
            collections_path=str(collections_dir),
        )
        creator.run()
        return collections_dir / name

    return _build


# ---------------------------------------------------------------------------
# Stubbed-HTTP cloud sources (jira / confluence / outline)
#
# Each fixture constructs the *real* reader + converter and stubs only the
# network at the ``read_documents`` boundary (the HTTP client the reader uses).
# The reader, converter, chunker, embedder and FAISS index all run for real on
# small fixtures. Each harness exposes ``add(...)`` to append a document to the
# backing store and ``make_reader()`` to build a fresh reader over the current
# store — used to drive the incremental-update leg of the lifecycle.
# ---------------------------------------------------------------------------


def _adf_paragraph(text: str) -> dict:
    """A minimal ADF doc wrapping ``text`` in one paragraph."""
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _jira_issue(key: str, summary: str, body: str, updated: str) -> dict:
    return {
        "key": key,
        "self": f"https://acme.atlassian.net/rest/api/2/issue/{key}",
        "fields": {
            "summary": summary,
            "updated": updated,
            "description": _adf_paragraph(body),
            "comment": {"comments": []},
        },
    }


def _fake_jira_class(issues: list[dict]):
    """A fake ``atlassian.Jira`` reading live from the shared ``issues`` list."""

    class _FakeJira:
        def __init__(self, **kwargs):
            pass

        def jql(self, jql, fields=None, start=0, limit=50, expand=None, **kwargs):
            batch = issues[start : start + limit]
            return {
                "issues": batch,
                "total": len(issues),
                "startAt": start,
                "maxResults": limit,
            }

        def enhanced_jql(
            self, jql, fields=None, nextPageToken=None, limit=50, expand=None, **kwargs
        ):
            start = int(nextPageToken) if nextPageToken else 0
            batch = issues[start : start + limit] if limit else issues[start:]
            result = {"issues": batch}
            nxt = start + len(batch)
            if nxt < len(issues):
                result["nextPageToken"] = str(nxt)
            return result

        def approximate_issue_count(self, jql):
            return {"count": len(issues)}

    return _FakeJira


@pytest.fixture
def jira_source(monkeypatch: pytest.MonkeyPatch):
    """Real Jira reader+converter with the ``atlassian.Jira`` client stubbed."""
    import connectors.jira.unified_jira_document_reader as reader_mod
    from connectors.jira.unified_jira_document_converter import (
        UnifiedJiraDocumentConverter,
    )
    from connectors.jira.unified_jira_document_reader import (
        JiraAuthType,
        UnifiedJiraDocumentReader,
    )

    issues = [
        _jira_issue(
            "JIRA-1",
            "Login page styling regression",
            "The CSS grid layout misaligns the header on mobile Safari browsers.",
            "2026-01-10T09:00:00.000+0000",
        ),
        _jira_issue(
            "JIRA-2",
            "Kubernetes autoscaler crash loop",
            "The horizontal pod autoscaler triggers repeated OOMKilled restarts "
            "during sustained burst traffic spikes on the payments cluster.",
            "2026-01-12T09:00:00.000+0000",
        ),
        _jira_issue(
            "JIRA-3",
            "Database migration plan",
            "We will shard the postgres users table by tenant identifier next quarter.",
            "2026-01-11T09:00:00.000+0000",
        ),
    ]
    monkeypatch.setattr(reader_mod, "Jira", _fake_jira_class(issues))

    def make_reader():
        return UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            batch_size=50,
            retry_delay=0,
            number_of_retries=1,
        )

    def add_update():
        issues.append(
            _jira_issue(
                "JIRA-4",
                "Redis session eviction",
                "The redis LRU eviction policy discards active session tokens "
                "prematurely under memory pressure on the auth service.",
                "2026-03-01T09:00:00.000+0000",
            )
        )
        return "JIRA-4", "redis LRU eviction active session tokens memory pressure"

    return SimpleNamespace(
        reader=make_reader(),
        converter=UnifiedJiraDocumentConverter(),
        make_reader=make_reader,
        add_update=add_update,
        reader_type="jiraCloud",
        needle_id="JIRA-2",
        needle_query="kubernetes horizontal pod autoscaler OOMKilled burst traffic",
    )


def _confluence_page(page_id: str, title: str, body_html: str, updated: str) -> dict:
    base_url = "https://confluence.example.com"
    return {
        "id": page_id,
        "title": title,
        "ancestors": [],
        "body": {"storage": {"value": body_html}},
        "version": {"when": updated},
        "_links": {
            "self": f"{base_url}/rest/api/content/{page_id}",
            "webui": f"/display/SPACE/{title.replace(' ', '+')}",
        },
        "children": {"comment": {"size": 0, "results": []}},
    }


def _fake_confluence_get(pages: list[dict]):
    """A fake ``requests.get`` for the sync Confluence reader, reading live."""

    class _Resp:
        def __init__(self, data):
            self._data = data
            self.status_code = 200

        def json(self):
            return self._data

        def raise_for_status(self):
            pass

    def fake_get(url, headers=None, params=None, auth=None, **kwargs):
        params = params or {}
        start = params.get("start", 0)
        limit = params.get("limit", 50)
        batch = pages[start : start + limit]
        return _Resp({"results": batch, "totalSize": len(pages)})

    return fake_get


@pytest.fixture
def confluence_source(monkeypatch: pytest.MonkeyPatch):
    """Real Confluence reader+converter with ``requests.get`` stubbed."""
    import connectors.confluence.confluence_document_reader as reader_mod
    from connectors.confluence.confluence_document_reader import (
        ConfluenceDocumentReader,
    )
    from connectors.confluence.unified_confluence_document_converter import (
        UnifiedConfluenceDocumentConverter,
    )

    pages = [
        _confluence_page(
            "201",
            "Onboarding Guide",
            "<h2>Welcome</h2><p>New engineers set up their laptop and VPN.</p>",
            "2026-01-10T10:00:00.000Z",
        ),
        _confluence_page(
            "202",
            "Incident Retrospective",
            "<h2>Summary</h2><p>The checkout service exhausted its database "
            "connection pool during the flash sale, causing cascading timeouts.</p>",
            "2026-01-12T10:00:00.000Z",
        ),
        _confluence_page(
            "203",
            "Release Calendar",
            "<h2>Schedule</h2><p>The mobile app ships on the first Tuesday monthly.</p>",
            "2026-01-11T10:00:00.000Z",
        ),
    ]
    monkeypatch.setattr(reader_mod.requests, "get", _fake_confluence_get(pages))

    def make_reader():
        return ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = DOCS",
            token="fake-token",
            batch_size=50,
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )

    def add_update():
        pages.append(
            _confluence_page(
                "204",
                "Security Review",
                "<h2>Findings</h2><p>The OAuth token refresh endpoint leaked "
                "scopes to third party integrations without consent.</p>",
                "2026-03-01T10:00:00.000Z",
            )
        )
        return "204", "oauth token refresh endpoint leaked scopes third party"

    return SimpleNamespace(
        reader=make_reader(),
        converter=UnifiedConfluenceDocumentConverter(is_cloud=False),
        make_reader=make_reader,
        add_update=add_update,
        reader_type="confluence",
        needle_id="202",
        needle_query="checkout database connection pool exhausted cascading timeouts",
    )


def _outline_document(doc_id: str, title: str, text: str, updated: str) -> dict:
    return {
        "id": doc_id,
        "title": title,
        "text": text,
        "url": f"https://app.getoutline.com/doc/{doc_id}",
        "updatedAt": updated,
        "collectionId": "col1",
        "parentDocumentId": None,
    }


class _OutlineResp:
    """Stand-in for both requests.Response and httpx.Response."""

    def __init__(self, payload=None, content=b"", headers=None, status=200):
        self.status_code = status
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}
        self.text = ""
        self.url = ""

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _OutlineAsyncClient:
    """Async context manager routing ``documents.info`` by request body id."""

    def __init__(self, docs_by_id):
        self._docs_by_id = docs_by_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        if "documents.info" in url:
            doc_id = (kwargs.get("json") or {}).get("id")
            return _OutlineResp(payload={"data": self._docs_by_id[doc_id]})
        raise AssertionError(f"unexpected outline POST {url}")

    async def get(self, url, **kwargs):
        raise AssertionError(f"unexpected outline GET {url}")


@pytest.fixture
def outline_source(monkeypatch: pytest.MonkeyPatch):
    """Real Outline reader+converter with sync + async HTTP stubbed.

    Attachments are disabled so only the ``documents.list`` (sync) and
    ``documents.info`` (async) endpoints are exercised.
    """
    from connectors.outline.outline_document_converter import OutlineDocumentConverter
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    docs = [
        _outline_document(
            "doc-a",
            "Design Principles",
            "We favour composition over inheritance and keep modules small.",
            "2026-01-10T00:00:00Z",
        ),
        _outline_document(
            "doc-b",
            "Runbook: Cache Warmup",
            "The nightly job pre-warms the recommendation feature store so the "
            "morning traffic peak does not stampede the cold cache.",
            "2026-01-12T00:00:00Z",
        ),
        _outline_document(
            "doc-c",
            "Team Charter",
            "Our mission is to make internal knowledge instantly searchable.",
            "2026-01-11T00:00:00Z",
        ),
    ]
    docs_by_id = {d["id"]: d for d in docs}

    def fake_post(url, **kwargs):
        if "documents.list" in url:
            stubs = [{"id": d["id"]} for d in docs]
            return _OutlineResp(
                payload={
                    "data": stubs,
                    "pagination": {
                        "offset": 0,
                        "limit": len(stubs),
                        "total": len(stubs),
                    },
                }
            )
        raise AssertionError(f"unexpected outline sync POST {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr(
        "connectors.outline.outline_document_reader.httpx.AsyncClient",
        lambda **kwargs: _OutlineAsyncClient(docs_by_id),
    )

    def make_reader():
        return OutlineDocumentReader(
            base_url="https://app.getoutline.com",
            api_token="ol_api_test",
            collection_ids=["col1"],
            batch_size=50,
            include_attachments=False,
            download_inline_images=False,
            number_of_retries=1,
            retry_delay=0.0,
        )

    def add_update():
        doc = _outline_document(
            "doc-d",
            "Deployment Postmortem",
            "The blue green deployment cutover dropped every in-flight websocket "
            "connection, forcing clients to reconnect and replay their state.",
            "2026-03-01T00:00:00Z",
        )
        docs.append(doc)
        docs_by_id[doc["id"]] = doc
        return (
            "doc-d",
            "blue green deployment cutover dropped in-flight websocket connections",
        )

    return SimpleNamespace(
        reader=make_reader(),
        converter=OutlineDocumentConverter(),
        make_reader=make_reader,
        add_update=add_update,
        reader_type="outline",
        needle_id="doc-b",
        needle_query="nightly job pre-warm recommendation feature store cold cache stampede",
    )
