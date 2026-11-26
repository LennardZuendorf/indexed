"""A truncated thread must say so in the chunk metadata (#356)."""

from unittest.mock import MagicMock

import pytest

from indexed.connectors.github.github_document_converter import GitHubDocumentConverter

pytestmark = pytest.mark.unit


def _document(**overrides) -> dict:
    base = {
        "id": "octo/hello#7",
        "url": "https://github.com/octo/hello/issues/7",
        "modifiedTime": "2026-06-20T10:00:00Z",
        "title": "Very long thread",
        "body": "",
        "state": "OPEN",
        "labels": [],
        "author": "octocat",
        "kind": "issue",
        "comments": [],
        "project_fields": {},
    }
    base.update(overrides)
    return base


def _converter_with_empty_parser() -> GitHubDocumentConverter:
    """Header chunk needs no parser; the document has no body so no other
    chunk is built."""
    parsed = MagicMock()
    parsed.chunks = []
    converter = GitHubDocumentConverter()
    converter._parser_instance = parsed
    return converter


def test_truncated_thread_stamps_limit_on_every_chunk():
    converter = _converter_with_empty_parser()
    document = _document(commentsTruncated=True, commentsLimit=1000)

    (converted,) = converter.convert(document)
    header_meta = converted["chunks"][0]["metadata"]

    assert header_meta["commentsTruncated"] is True
    assert header_meta["commentsLimit"] == 1000


def test_complete_thread_carries_no_truncation_fields():
    converter = _converter_with_empty_parser()

    (converted,) = converter.convert(_document())
    header_meta = converted["chunks"][0]["metadata"]

    assert "commentsTruncated" not in header_meta
    assert "commentsLimit" not in header_meta
