"""Full-pipeline CLI E2E: `index create {outline,jira,confluence} -> index search`
against a localhost pytest-httpserver stub.

Unlike ``test_connectors_e2e.py`` (reader -> converter only, SDK monkeypatched),
this module drives the *real* Typer CLI end to end: HTTP stub -> reader ->
converter -> chunker -> embedder -> FAISS index -> on-disk persistence ->
search. Only the reader-level HTTP is faked (via ``tests/fixtures/connectors``);
everything downstream is exercised for real.

Scope (Plan A): Outline (self-hosted shape), Jira Server/DC, Confluence
Server/DC -- the three connectors that work against a plain ``http://localhost``
stub with no Atlassian Cloud (`.atlassian.net`) gate. Cloud connectors are out
of scope here (Phase B).

Beyond the exit-0 happy path, this module also hardens the stub itself:
auth-header enforcement (a wrong token must fail, not silently pass),
Outline's attachment/redirect download path, Confluence's default
``read_all_comments=True`` mode, and offset-aware pagination across multiple
pages. See ``tests/fixtures/connectors/stub_routes.py`` for the stub-side half
of each of these.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner

from indexed.cli.app import app
from indexed.config.service import reload as reload_config
from tests.fixtures.connectors import payloads, stub_routes

pytestmark = pytest.mark.connectors

_STUB_TOKEN = "stub-token"


# --------------------------------------------------------------------------- #
# Isolation fixture                                                            #
# --------------------------------------------------------------------------- #
@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolate global storage (``~/.indexed``) AND cwd-based local-mode
    auto-detection to a throwaway tmp dir for the duration of one test.

    ``ConfigService`` is a cached singleton (``config/service.py``); ``reload()``
    drops it so a freshly-set ``HOME`` is actually picked up. Storage-mode
    auto-detection also inspects the *current working directory* for a local
    ``.indexed/config.toml`` (``config/storage.py``), so ``HOME`` alone is not
    sufficient isolation -- the cwd must move too, or a stray local
    ``.indexed/`` at the repo root would silently redirect writes there.

    The embedding model cache (``~/.cache/huggingface``) is HOME-relative too,
    so faking ``HOME`` would hide the already-downloaded model and force an
    (offline-blocked) re-download. Indexed's own cache check
    (``model_manager._get_hf_cache_dir``) reads ``HF_HOME`` via
    ``os.environ.get`` at call time and appends ``/hub`` itself, so it wants
    the *parent* ``huggingface`` dir. ``SentenceTransformer.__init__`` reads
    ``SENTENCE_TRANSFORMERS_HOME`` separately (also at call time) and passes
    it straight through as ``cache_dir`` to the HF loader, which expects the
    ``hub`` subdirectory directly -- passing the parent dir there silently
    breaks the offline cache lookup (verified empirically: it falls through
    to a live network HEAD request that fails under ``HF_HUB_OFFLINE=1``,
    misreported as "couldn't connect"). Point each var at the directory level
    its own reader expects.

    The real home directory MUST be read via ``os.environ["HOME"]`` (or
    ``os.path.expanduser``), NOT ``Path.home()`` -- the session-scoped
    ``isolate_config_paths`` autouse fixture in ``tests/conftest.py`` already
    monkeypatches ``Path.home`` to a sandbox dir for the whole test session,
    so calling ``Path.home()`` here would silently capture that sandbox
    (which has no cached model) instead of the real cache location.

    Storage root resolution (``config/storage.py:get_global_root`` ->
    ``Path.home() / ".indexed"``) itself calls ``Path.home()``, which the
    session fixture has already patched to its own sandbox -- setting the
    ``HOME`` env var here has NO effect on it (``Path.home()`` on POSIX does
    consult ``HOME``, but the session fixture's ``monkeypatch.setattr``
    replaces the method entirely, short-circuiting env-var resolution). Since
    every test still shares the *same* session sandbox, collections from
    different tests in this module would collide there. Re-patch
    ``Path.home`` (on top of the session patch; function-scoped ``monkeypatch``
    auto-reverts to the session sandbox after this test) to point at
    ``tmp_path`` for true per-test isolation.
    """
    real_hf_home = Path(os.environ["HOME"]) / ".cache" / "huggingface"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HF_HOME", str(real_hf_home))
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(real_hf_home / "hub"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TQDM_DISABLE", "1")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    reload_config()
    yield tmp_path
    reload_config()


def _collection_dir(home: Path, name: str) -> Path:
    return home / ".indexed" / "data" / "collections" / name


def _assert_pipeline_artifacts(
    coll: Path, *, expected_doc_id: str, seed_phrase: str
) -> None:
    """Assert manifest.json / per-document json / FAISS index were all written
    with the expected shape, per the real on-disk layout written by
    ``documents_collection_creator.py`` (NOT the design doc's simplified
    ``documents.json``/``index.faiss`` names).
    """
    manifest_path = coll / "manifest.json"
    assert manifest_path.exists(), f"manifest.json missing under {coll}"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["numberOfDocuments"] == 1
    assert manifest["numberOfChunks"] >= 1

    doc_files = list((coll / "documents").glob("*.json"))
    assert len(doc_files) == 1, f"expected exactly one document file, got {doc_files}"
    doc = json.loads(doc_files[0].read_text())
    assert doc["id"] == expected_doc_id
    assert set(doc.keys()) >= {"id", "url", "modifiedTime", "text", "chunks"}
    assert seed_phrase in doc["text"]
    assert len(doc["chunks"]) >= 1

    faiss_files = list(coll.rglob("*.faiss"))
    assert faiss_files, f"no .faiss index written under {coll}"


# --------------------------------------------------------------------------- #
# Outline (self-hosted shape; cloud+self-hosted share the same reader)         #
# --------------------------------------------------------------------------- #
def test_outline_e2e_create_and_search(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url = httpserver.url_for("").rstrip("/")

    doc_info = payloads.outline_document_info()
    stub_routes.register_outline(
        httpserver,
        documents=[doc_info],
        expected_token=_STUB_TOKEN,
    )

    monkeypatch.setenv("OUTLINE_API_TOKEN", _STUB_TOKEN)

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "outline",
            "--collection",
            "ol-e2e",
            "--url",
            base_url,
            "--collection-id",
            "col1",
            "--no-include-attachments",
            "--no-ocr",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code == 0, create_result.stdout

    coll = _collection_dir(isolated_home, "ol-e2e")
    _assert_pipeline_artifacts(
        coll,
        expected_doc_id=doc_info["id"],
        seed_phrase="rotate the vault token",
    )

    search_result = runner.invoke(
        app,
        [
            "index",
            "search",
            "rotate the vault token",
            "--collection",
            "ol-e2e",
            "--compact",
        ],
        catch_exceptions=False,
    )
    assert search_result.exit_code == 0, search_result.stdout
    assert doc_info["id"] in search_result.stdout


def test_outline_e2e_wrong_auth_fails(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request carrying the wrong bearer token must fail the create, not
    silently succeed.

    Regression guard: the stub used to answer every request regardless of
    the ``Authorization`` header, so a misconfigured/rotated token would
    "index successfully" against the stub while a real Outline instance
    would reject it with 401 -- a false-green gap.
    """
    base_url = httpserver.url_for("").rstrip("/")

    doc_info = payloads.outline_document_info()
    stub_routes.register_outline(
        httpserver,
        documents=[doc_info],
        expected_token=_STUB_TOKEN,
    )

    monkeypatch.setenv("OUTLINE_API_TOKEN", "wrong-token")

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "outline",
            "--collection",
            "ol-e2e-badauth",
            "--url",
            base_url,
            "--collection-id",
            "col1",
            "--no-include-attachments",
            "--no-ocr",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code != 0, create_result.stdout
    coll = _collection_dir(isolated_home, "ol-e2e-badauth")
    assert not (coll / "manifest.json").exists()


def test_outline_e2e_attachments_and_redirect(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--include-attachments`` exercises the ``attachments.list`` ->
    ``attachments.redirect`` (real 302, followed to a same-origin bytes
    route) download path end to end.

    Regression guard: these two routes were previously unregistered, so any
    attempt to write this test against the old stub would fail outright
    (``attachments.list``/``attachments.redirect`` are hit unconditionally
    when ``include_attachments=True``, which is also the connector's
    default).
    """
    base_url = httpserver.url_for("").rstrip("/")

    doc_info = payloads.outline_document_info()
    attachment_stub = payloads.outline_attachment_stub(att_id="att1", name="notes.txt")
    attachment_seed = "quarterly key rotation checklist lives in this attachment"
    stub_routes.register_outline(
        httpserver,
        documents=[doc_info],
        expected_token=_STUB_TOKEN,
        attachments_by_doc_id={doc_info["id"]: [attachment_stub]},
        attachment_bytes_by_id={
            "att1": (attachment_seed.encode("utf-8"), "text/plain")
        },
    )

    monkeypatch.setenv("OUTLINE_API_TOKEN", _STUB_TOKEN)

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "outline",
            "--collection",
            "ol-e2e-attach",
            "--url",
            base_url,
            "--collection-id",
            "col1",
            "--include-attachments",
            "--no-ocr",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code == 0, create_result.stdout

    coll = _collection_dir(isolated_home, "ol-e2e-attach")
    _assert_pipeline_artifacts(
        coll,
        expected_doc_id=doc_info["id"],
        seed_phrase="rotate the vault token",
    )
    doc_files = list((coll / "documents").glob("*.json"))
    doc = json.loads(doc_files[0].read_text())
    assert any(attachment_seed in chunk["indexedData"] for chunk in doc["chunks"]), (
        "attachment bytes downloaded via attachments.redirect were never chunked"
    )

    search_result = runner.invoke(
        app,
        [
            "index",
            "search",
            attachment_seed,
            "--collection",
            "ol-e2e-attach",
            "--compact",
        ],
        catch_exceptions=False,
    )
    assert search_result.exit_code == 0, search_result.stdout
    assert doc_info["id"] in search_result.stdout


def test_outline_e2e_pagination_multi_page(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dataset larger than one stub page must be read across multiple
    ``documents.list`` requests, and the read must terminate with every
    document accounted for.

    Regression guard: the stub used to echo the same static first page for
    every request regardless of the requested offset, so a >1-page dataset
    would come back truncated/duplicated instead of exercising real
    pagination. ``page_size=1`` here forces 3 requests even though the
    reader asks for its normal (50-doc) batch size.
    """
    base_url = httpserver.url_for("").rstrip("/")

    docs = [
        payloads.outline_document_info(
            doc_id=f"page-doc-{i}", text=f"unique offset marker number {i} of three"
        )
        for i in range(1, 4)
    ]
    stub_routes.register_outline(
        httpserver,
        documents=docs,
        expected_token=_STUB_TOKEN,
        page_size=1,
    )

    monkeypatch.setenv("OUTLINE_API_TOKEN", _STUB_TOKEN)

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "outline",
            "--collection",
            "ol-e2e-paged",
            "--url",
            base_url,
            "--collection-id",
            "col1",
            "--no-include-attachments",
            "--no-ocr",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code == 0, create_result.stdout

    coll = _collection_dir(isolated_home, "ol-e2e-paged")
    manifest = json.loads((coll / "manifest.json").read_text())
    assert manifest["numberOfDocuments"] == len(docs)

    doc_files = list((coll / "documents").glob("*.json"))
    assert len(doc_files) == len(docs)
    persisted_ids = {json.loads(f.read_text())["id"] for f in doc_files}
    assert persisted_ids == {d["id"] for d in docs}

    search_result = runner.invoke(
        app,
        [
            "index",
            "search",
            "unique offset marker number 3 of three",
            "--collection",
            "ol-e2e-paged",
            "--compact",
        ],
        catch_exceptions=False,
    )
    assert search_result.exit_code == 0, search_result.stdout
    assert "page-doc-3" in search_result.stdout


# --------------------------------------------------------------------------- #
# Jira Server/DC                                                               #
# --------------------------------------------------------------------------- #
def test_jira_server_e2e_create_and_search(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url = httpserver.url_for("").rstrip("/")

    issue = payloads.jira_server_issue(base_url=base_url)
    stub_routes.register_jira_server(
        httpserver, issues=[issue], expected_token=_STUB_TOKEN
    )

    monkeypatch.setenv("JIRA_TOKEN", _STUB_TOKEN)

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "jira",
            "--collection",
            "jira-e2e",
            "--url",
            base_url,
            "--jql",
            "project = SRV",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code == 0, create_result.stdout

    coll = _collection_dir(isolated_home, "jira-e2e")
    _assert_pipeline_artifacts(
        coll,
        expected_doc_id=issue["key"],
        seed_phrase="database timeout on staging",
    )

    search_result = runner.invoke(
        app,
        [
            "index",
            "search",
            "database timeout on staging",
            "--collection",
            "jira-e2e",
            "--compact",
        ],
        catch_exceptions=False,
    )
    assert search_result.exit_code == 0, search_result.stdout
    assert issue["key"] in search_result.stdout


def test_jira_server_e2e_wrong_auth_fails(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request carrying the wrong bearer token must fail the create.

    Jira auth goes through ``atlassian-python-api`` (a different HTTP code
    path than Confluence/Outline's direct ``requests`` calls), so this is a
    separate regression guard on the same stub gap.
    """
    base_url = httpserver.url_for("").rstrip("/")

    issue = payloads.jira_server_issue(base_url=base_url)
    stub_routes.register_jira_server(
        httpserver, issues=[issue], expected_token=_STUB_TOKEN
    )

    monkeypatch.setenv("JIRA_TOKEN", "wrong-token")

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "jira",
            "--collection",
            "jira-e2e-badauth",
            "--url",
            base_url,
            "--jql",
            "project = SRV",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code != 0, create_result.stdout
    coll = _collection_dir(isolated_home, "jira-e2e-badauth")
    assert not (coll / "manifest.json").exists()


# --------------------------------------------------------------------------- #
# Confluence Server/DC                                                        #
# --------------------------------------------------------------------------- #
def test_confluence_server_e2e_create_and_search(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url = httpserver.url_for("").rstrip("/")

    page = payloads.confluence_server_page(base_url=base_url)
    stub_routes.register_confluence_server(
        httpserver, pages=[page], expected_token=_STUB_TOKEN
    )

    monkeypatch.setenv("CONF_TOKEN", _STUB_TOKEN)

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "confluence",
            "--collection",
            "conf-e2e",
            "--url",
            base_url,
            "--cql",
            "type=page",
            "--first-level-comments",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code == 0, create_result.stdout

    coll = _collection_dir(isolated_home, "conf-e2e")
    _assert_pipeline_artifacts(
        coll,
        expected_doc_id=page["id"],
        seed_phrase="Install the package with pip",
    )

    search_result = runner.invoke(
        app,
        [
            "index",
            "search",
            "Install the package with pip",
            "--collection",
            "conf-e2e",
            "--compact",
        ],
        catch_exceptions=False,
    )
    assert search_result.exit_code == 0, search_result.stdout
    assert page["id"] in search_result.stdout


def test_confluence_server_e2e_wrong_auth_fails(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request carrying the wrong bearer token must fail the create."""
    base_url = httpserver.url_for("").rstrip("/")

    page = payloads.confluence_server_page(base_url=base_url)
    stub_routes.register_confluence_server(
        httpserver, pages=[page], expected_token=_STUB_TOKEN
    )

    monkeypatch.setenv("CONF_TOKEN", "wrong-token")

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "confluence",
            "--collection",
            "conf-e2e-badauth",
            "--url",
            base_url,
            "--cql",
            "type=page",
            "--first-level-comments",
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code != 0, create_result.stdout
    coll = _collection_dir(isolated_home, "conf-e2e-badauth")
    assert not (coll / "manifest.json").exists()


def test_confluence_server_e2e_default_read_all_comments(
    isolated_home: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The connector's *default* comment mode (``read_all_comments=True``,
    i.e. no ``--first-level-comments`` flag) issues a separate paginated
    request to ``/rest/api/content/{id}/child/comment`` and must fold that
    comment body into the indexed document.

    Regression guard: previously only ``--first-level-comments``
    (``read_all_comments=False``) was tested, so the default mode's separate
    comment-fetch request path was never exercised -- writing this test
    against the old stub would fail outright since that endpoint wasn't
    registered at all.
    """
    base_url = httpserver.url_for("").rstrip("/")

    page = payloads.confluence_server_page(base_url=base_url, comment_count=1)
    comment_seed = "escalate to the platform team if retries are exhausted"
    stub_routes.register_confluence_server(
        httpserver,
        pages=[page],
        expected_token=_STUB_TOKEN,
        comments_by_page_id={
            page["id"]: [payloads.confluence_comment(f"<p>{comment_seed}</p>")]
        },
    )

    monkeypatch.setenv("CONF_TOKEN", _STUB_TOKEN)

    runner = CliRunner()
    create_result = runner.invoke(
        app,
        [
            "index",
            "create",
            "confluence",
            "--collection",
            "conf-e2e-allcomments",
            "--url",
            base_url,
            "--cql",
            "type=page",
            # No --first-level-comments / --read-all-comments flag: exercises
            # the connector's default (read_all_comments=True).
            "--no-cache",
            "--force",
        ],
        catch_exceptions=False,
    )
    assert create_result.exit_code == 0, create_result.stdout

    coll = _collection_dir(isolated_home, "conf-e2e-allcomments")
    _assert_pipeline_artifacts(
        coll,
        expected_doc_id=page["id"],
        seed_phrase="Install the package with pip",
    )
    doc_files = list((coll / "documents").glob("*.json"))
    doc = json.loads(doc_files[0].read_text())
    assert comment_seed in doc["text"], (
        "comment fetched via the default read_all_comments=True endpoint "
        "was never folded into the document text"
    )

    search_result = runner.invoke(
        app,
        [
            "index",
            "search",
            comment_seed,
            "--collection",
            "conf-e2e-allcomments",
            "--compact",
        ],
        catch_exceptions=False,
    )
    assert search_result.exit_code == 0, search_result.stdout
    assert page["id"] in search_result.stdout
