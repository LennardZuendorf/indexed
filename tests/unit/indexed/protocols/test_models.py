"""Tests for shared protocol DTOs and the typed data contracts (foundation/7).

The on-disk v1 JSON format is the compatibility boundary for the v2 core swap:
the typed models MUST round-trip today's camelCase collection JSON byte-stable,
so existing collections keep loading. These tests pin that contract for the
manifest (all four sources, plus a pre-``createdTime`` collection) and for the
converted-document/chunk shape.
"""

import json

from indexed.protocols import SourceConfig
from indexed.protocols.models import (
    Chunk,
    CollectionSearchResult,
    ConvertedDocument,
    DocumentMatch,
    Manifest,
    MatchedChunk,
)


def test_source_config_reader_opts_default() -> None:
    cfg = SourceConfig(
        name="c", type="outline", base_url_or_path="https://x.example.com"
    )
    assert cfg.reader_opts == {}
    assert cfg.query is None


# Reader-detail blocks exactly as each source's get_reader_details() emits them.
_FILES_READER = {
    "type": "localFiles",
    "basePath": "/home/user/docs",
    "includePatterns": ["*.md", "*.py"],
    "failFast": False,
    "respectGitignore": True,
    "excludedDirs": [".git", "node_modules"],
}
_JIRA_CLOUD_READER = {
    "type": "jiraCloud",
    "baseUrl": "https://acme.atlassian.net",
    "query": "project = ENG",
    "batchSize": 100,
    "fields": "summary,description,comment",
}
_CONFLUENCE_CLOUD_READER = {
    "type": "confluenceCloud",
    "baseUrl": "https://acme.atlassian.net/wiki",
    "query": "space = DOCS",
    "expand": "body.storage",
    "batchSize": 50,
    "readAllComments": True,
}
_OUTLINE_READER = {
    "type": "outline",
    "baseUrl": "https://outline.acme.com",
    "collectionIds": ["col-1", "col-2"],
    "batchSize": 25,
    "includeAttachments": True,
    "downloadInlineImages": False,
    "maxConcurrentRequests": 5,
    "maxAttachmentSizeMb": 20,
    "verifySsl": True,
    "ocrEnabled": False,
}


def _manifest(reader: dict, *, created: bool = True) -> dict:
    """Build an on-disk manifest dict in the exact key order the creator writes."""
    m: dict = {"collectionName": "my-collection"}
    if created:
        m["createdTime"] = "2026-07-06T10:00:00+00:00"
    m["updatedTime"] = "2026-07-07T11:30:00+00:00"
    m["lastModifiedDocumentTime"] = "2026-07-05T09:15:00+00:00"
    m["numberOfDocuments"] = 12
    m["numberOfChunks"] = 480
    m["reader"] = reader
    m["indexers"] = [{"name": "faiss-flat-l2"}]
    return m


def _byte_stable(raw: dict) -> None:
    """Assert Manifest.from_disk(raw).to_disk() reproduces raw byte-for-byte."""
    result = Manifest.from_disk(raw).to_disk()
    assert result == raw
    # order-sensitive equality == byte stability under a deterministic dumper
    assert json.dumps(result) == json.dumps(raw)
    assert list(result.keys()) == list(raw.keys())
    assert list(result["reader"].keys()) == list(raw["reader"].keys())


def test_manifest_roundtrip_files():
    _byte_stable(_manifest(_FILES_READER))


def test_manifest_roundtrip_jira_cloud():
    _byte_stable(_manifest(_JIRA_CLOUD_READER))


def test_manifest_roundtrip_confluence_cloud():
    _byte_stable(_manifest(_CONFLUENCE_CLOUD_READER))


def test_manifest_roundtrip_outline():
    _byte_stable(_manifest(_OUTLINE_READER))


def test_manifest_roundtrip_pre_created_time_collection():
    """A collection written before the createdTime key must not gain one."""
    raw = _manifest(_FILES_READER, created=False)
    assert "createdTime" not in raw
    result = Manifest.from_disk(raw).to_disk()
    assert "createdTime" not in result
    _byte_stable(raw)


def test_manifest_typed_field_access():
    m = Manifest.from_disk(_manifest(_JIRA_CLOUD_READER))
    assert m.collection_name == "my-collection"
    assert m.reader.type == "jiraCloud"
    assert m.indexers[0].name == "faiss-flat-l2"
    assert m.number_of_documents == 12


def test_manifest_update_preserves_reader_and_created_time():
    """The update path mutates four fields and keeps everything else stable."""
    raw = _manifest(_OUTLINE_READER)
    m = Manifest.from_disk(raw)
    m.updated_time = "2026-07-08T00:00:00+00:00"
    m.number_of_documents = 15
    out = m.to_disk()
    assert out["updatedTime"] == "2026-07-08T00:00:00+00:00"
    assert out["numberOfDocuments"] == 15
    assert out["createdTime"] == raw["createdTime"]
    assert out["reader"] == _OUTLINE_READER
    assert list(out.keys()) == list(raw.keys())


# --- ConvertedDocument / Chunk -------------------------------------------------

_CONVERTED_DOC = {
    "id": "utils/retry.py",
    "url": "file:///home/user/docs/utils/retry.py",
    "modifiedTime": "2026-06-01T12:00:00",
    "text": "utils/retry.py\n\nfull contextualized text",
    "chunks": [
        {"indexedData": "utils/retry.py"},  # chunk 0: path, NO metadata key
        {"indexedData": "def retry(): ...", "metadata": {"lines": "1-10"}},
    ],
}


def test_converted_document_roundtrip():
    result = ConvertedDocument.model_validate(_CONVERTED_DOC).to_disk()
    assert result == _CONVERTED_DOC
    assert json.dumps(result) == json.dumps(_CONVERTED_DOC)
    # chunk 0 must stay metadata-free (byte-stability caveat)
    assert "metadata" not in result["chunks"][0]
    assert result["chunks"][1]["metadata"] == {"lines": "1-10"}


def test_chunk_omits_absent_metadata():
    assert Chunk(indexed_data="x").to_disk() == {"indexedData": "x"}
    assert Chunk(indexed_data="x", metadata={"a": 1}).to_disk() == {
        "indexedData": "x",
        "metadata": {"a": 1},
    }


# --- Search result models ------------------------------------------------------


def test_collection_search_result_construction():
    res = CollectionSearchResult(
        collection_name="c",
        indexer_name="faiss-flat-l2",
        results=[
            DocumentMatch(
                id="d1",
                url="file:///d1",
                path="d1",
                matched_chunks=[MatchedChunk(chunk_number=0, score=0.5)],
            )
        ],
    )
    assert res.error is None
    assert res.results[0].matched_chunks[0].score == 0.5


def test_collection_search_result_error_channel():
    res = CollectionSearchResult(
        collection_name="c", indexer_name="i", error="index failed"
    )
    assert res.error == "index failed"
    assert res.results == []
