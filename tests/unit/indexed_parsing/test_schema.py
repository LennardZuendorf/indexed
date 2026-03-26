"""Tests for parsing.schema — ParsedChunk and ParsedDocument."""

from parsing.schema import ParsedChunk, ParsedDocument


def test_parsed_chunk_content_hash_deterministic():
    """Same text always produces the same content_hash."""
    c1 = ParsedChunk(text="hello", contextualized_text="hello")
    c2 = ParsedChunk(text="hello", contextualized_text="hello")
    assert c1.content_hash == c2.content_hash
    assert c1.content_hash != ""


def test_parsed_chunk_different_text_different_hash():
    c1 = ParsedChunk(text="hello", contextualized_text="hello")
    c2 = ParsedChunk(text="world", contextualized_text="world")
    assert c1.content_hash != c2.content_hash


def test_parsed_chunk_metadata_defaults():
    c = ParsedChunk(text="x", contextualized_text="x")
    assert c.metadata == {}
    assert c.source_type == "plaintext"


def test_parsed_document_defaults():
    doc = ParsedDocument(file_path="/tmp/test.txt")
    assert doc.chunks == []
    assert doc.metadata == {}


def test_parsed_document_with_chunks():
    chunks = [
        ParsedChunk(text="a", contextualized_text="a", source_type="code"),
        ParsedChunk(text="b", contextualized_text="b", source_type="document"),
    ]
    doc = ParsedDocument(file_path="f.py", chunks=chunks, metadata={"size": 100})
    assert len(doc.chunks) == 2
    assert doc.metadata["size"] == 100
