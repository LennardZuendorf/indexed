from unittest.mock import MagicMock, patch

import pytest

from indexed.connectors.github.github_document_converter import GitHubDocumentConverter

pytestmark = pytest.mark.unit


def _document(**overrides) -> dict:
    base = {
        "id": "octo/hello#7",
        "url": "https://github.com/octo/hello/issues/7",
        "modifiedTime": "2026-06-20T10:00:00Z",
        "title": "Flaky retry logic",
        "body": "The retry loop sometimes doubles up.",
        "state": "OPEN",
        "labels": ["bug"],
        "author": "octocat",
        "kind": "issue",
        "comments": [{"author": "reviewer", "body": "Can repro."}],
        "project_fields": {},
    }
    base.update(overrides)
    return base


def _fake_parsed_chunk(text: str, metadata: dict | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.contextualized_text = text
    chunk.metadata = metadata or {}
    return chunk


def test_yields_one_document_with_header_and_body_chunks():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("The retry loop sometimes doubles up.")]

    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(_document()))

    assert result["id"] == "octo/hello#7"
    assert result["url"] == "https://github.com/octo/hello/issues/7"
    assert result["modifiedTime"] == "2026-06-20T10:00:00Z"
    assert len(result["chunks"]) == 3  # header + body + 1 comment
    assert "Flaky retry logic" in result["chunks"][0]["indexedData"]
    assert result["chunks"][1]["indexedData"] == "The retry loop sometimes doubles up."


def test_comment_chunks_include_author():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("body text")]

    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(_document()))

    comment_chunk = result["chunks"][-1]
    assert "reviewer" in comment_chunk["indexedData"]
    assert "Can repro." in comment_chunk["indexedData"]
    assert comment_chunk["metadata"]["commentAuthor"] == "reviewer"


def test_project_fields_attached_to_metadata():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("body text")]

    doc = _document(project_fields={"Status": "In Progress"})
    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(doc))

    assert result["chunks"][0]["metadata"]["projectFields"] == {"Status": "In Progress"}


def test_parse_failure_falls_back_to_raw_body():
    converter = GitHubDocumentConverter()

    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(
                parse_bytes=MagicMock(side_effect=RuntimeError("boom"))
            )
        ),
    ):
        (result,) = list(converter.convert(_document()))

    assert any("doubles up" in c["indexedData"] for c in result["chunks"])


def test_empty_body_yields_no_body_chunk():
    converter = GitHubDocumentConverter()
    doc = _document(body="", comments=[])
    (result,) = list(converter.convert(doc))
    assert len(result["chunks"]) == 1  # header only


def test_draft_item_without_url_still_converts():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("draft body")]

    doc = _document(
        id="project:PVTI_2", url="", kind="draft", state="DRAFT", comments=[]
    )
    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(doc))

    assert result["url"] == ""
    assert result["id"] == "project:PVTI_2"
