"""One query, three sources, and a payload that names the one that died (#340).

The fixture is the card's fixture, built for real: a workspace whose
``indexed.toml`` selects a GitHub-issues collection, a Markdown wiki and a code
collection, each holding a known answer. Nothing here loads an embedding model —
the collections are written directly (``seed_v1_collection``) and only the query
vector is stubbed — so the test proves the *payload contract*, which is what
this card is about.

What must never come back: a source that did not answer being indistinguishable
from a source that matched nothing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli.knowledge.commands import search as search_cmd
from indexed.connectors.github.github_document_converter import GitHubDocumentConverter
from tests.conftest import DEFAULT_INDEXER_NAME, seed_v1_collection

pytestmark = pytest.mark.indexed

QUERY = "how do I rotate the signing key"

ISSUES = "fixture-issues"
WIKI = "fixture-wiki"
CODE = "fixture-code"

LONG_COMMENT = (
    "We rotate the signing key by publishing the new key in JWKS first, then "
    "swapping the signer, then retiring the old public key after one cache TTL. "
) * 300  # ~30 KB: one comment, not one hit


def _github_document() -> dict:
    """A sanitized issue whose answer lives in a comment, written as the reader emits it."""
    document = {
        "id": "acme/widget#7",
        "url": "https://github.com/acme/widget/issues/7",
        "modifiedTime": "2026-01-02T00:00:00Z",
        "title": "Signing key rotation runbook",
        "body": "How do we rotate the signing key without breaking verifiers?",
        "state": "OPEN",
        "labels": ["ops"],
        "author": "octocat",
        "kind": "issue",
        "comments": [
            {
                "id": "IC_kwDO_1",
                "url": "https://github.com/acme/widget/issues/7#issuecomment-9001",
                "author": "reviewer",
                "body": LONG_COMMENT,
            }
        ],
        "project_fields": {},
    }
    (converted,) = list(GitHubDocumentConverter().convert(document))
    return converted


def _seed(collections_dir: Path) -> None:
    seed_v1_collection(
        collections_dir,
        ISSUES,
        reader_type="github",
        documents=[_github_document()],
    )
    seed_v1_collection(
        collections_dir,
        WIKI,
        documents=[
            {
                "id": "docs/ops/key-rotation.md",
                "url": "file:///repo/docs/ops/key-rotation.md",
                "text": "# Key rotation\n\nRotate the signing key every 90 days.",
                "chunks": [
                    {
                        "indexedData": (
                            "# Key rotation\n\nRotate the signing key every 90 days; "
                            "publish the new key in JWKS before swapping the signer."
                        ),
                        "metadata": {"headings": ["Key rotation"]},
                    }
                ],
            }
        ],
    )
    seed_v1_collection(
        collections_dir,
        CODE,
        documents=[
            {
                "id": "src/signing.py",
                "url": "",
                "text": "def rotate_signing_key(): ...",
                "chunks": [
                    {
                        "indexedData": (
                            "def rotate_signing_key(store):\n"
                            '    """Publish the new key in JWKS, then swap the signer."""'
                        ),
                        "metadata": {
                            "file_path": "/repo/src/signing.py",
                            "start_line": 41,
                            "end_line": 44,
                            "language": "python",
                        },
                    }
                ],
            }
        ],
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_sentence_embedder):
    """A workspace whose definition selects the three seeded collections."""
    from indexed.config import get_collections_path, get_global_root

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TQDM_DISABLE", "1")
    collections_dir = get_collections_path(get_global_root())
    collections_dir.mkdir(parents=True, exist_ok=True)
    _seed(collections_dir)

    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "indexed.toml").write_text(
        f'version = 1\n\n[collections]\nuse = ["{ISSUES}", "{WIKI}", "{CODE}"]\n'
    )
    monkeypatch.chdir(workspace)
    return workspace


runner = CliRunner()


def _search() -> dict:
    result = runner.invoke(search_cmd.app, [QUERY, "--json"])
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _hits_by_collection(payload: dict) -> dict[str, list[dict]]:
    hits: dict[str, list[dict]] = {}
    for document in payload["documents"]:
        hits.setdefault(document["collection"], []).extend(document["hits"])
    return hits


def _sources(payload: dict) -> dict[str, dict]:
    return {source["collection"]: source for source in payload["sources"]}


def test_each_source_is_citable(project: Path) -> None:
    """R1 — every source answers, and every hit resolves to where it came from."""
    payload = _search()

    assert payload["schema"] == "indexed.search/1"
    assert [source["collection"] for source in payload["sources"]] == [
        ISSUES,
        WIKI,
        CODE,
    ]
    assert {source["status"] for source in payload["sources"]} == {"ok"}

    hits = _hits_by_collection(payload)
    assert set(hits) == {ISSUES, WIKI, CODE}

    # The issue hit is cited as the comment under the issue.
    comment_urls = [hit["url"] for hit in hits[ISSUES] if hit.get("url")]
    assert comment_urls
    assert all(url.endswith("#issuecomment-9001") for url in comment_urls)

    # The wiki hit carries the heading path of the page it came from.
    wiki = payload["documents"][
        [d["collection"] for d in payload["documents"]].index(WIKI)
    ]
    assert wiki["path"].endswith("key-rotation.md")

    # The code hit carries the file and the 1-based line span.
    code = payload["documents"][
        [d["collection"] for d in payload["documents"]].index(CODE)
    ]
    assert code["path"] == "/repo/src/signing.py"
    assert code["hits"][0]["locator"]["kind"] == "line_span"
    assert code["hits"][0]["locator"]["start_line"] == 42


def test_a_deleted_source_leaves_the_others_answering(project: Path) -> None:
    """R4 — the failure this card exists to prevent: one dead source, one silent query."""
    from indexed.config import get_collections_path, get_global_root

    shutil.rmtree(get_collections_path(get_global_root()) / CODE)

    payload = _search()

    assert payload["collections"] == [ISSUES, WIKI]
    assert set(_hits_by_collection(payload)) == {ISSUES, WIKI}
    sources = _sources(payload)
    assert sources[CODE]["status"] == "missing"
    assert CODE in sources[CODE]["error"]
    assert "indexed.toml" in sources[CODE]["error"]
    assert [error["collection"] for error in payload["collection_errors"]] == [CODE]


def test_an_emptied_source_is_reported_empty(project: Path) -> None:
    """R3 — zero documents must never read as "nothing matched"."""
    from indexed.config import get_collections_path, get_global_root

    collection = get_collections_path(get_global_root()) / WIKI
    index = collection / "indexes" / DEFAULT_INDEXER_NAME / "indexer.faiss"
    import faiss

    faiss.write_index(faiss.IndexIDMap(faiss.IndexFlatL2(384)), str(index))

    payload = _search()

    sources = _sources(payload)
    assert sources[WIKI]["status"] == "empty"
    assert "indexes no documents" in sources[WIKI]["error"]
    assert WIKI not in _hits_by_collection(payload)
    assert any(
        error["collection"] == WIKI and "indexes no documents" in error["error"]
        for error in payload["collection_errors"]
    )


def test_payload_and_hit_text_stay_bounded(project: Path) -> None:
    """R5 — a 30 KB comment becomes several bounded hits, never one giant one.

    The whole payload for this fixture measures ~34.7 kB, of which 32 chunked
    hits make up the bulk; the 30 KB comment itself is never one hit.
    """
    import faiss  # noqa: F401 - imported by the fixture path

    payload = _search()
    hits = _hits_by_collection(payload)[ISSUES]

    assert len(hits) > 1, "a long comment is chunked like any other body"
    assert max(len(hit["text"]) for hit in hits) < 3000
    assert len(json.dumps(payload)) < 40_000
