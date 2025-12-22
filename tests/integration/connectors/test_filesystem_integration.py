"""Integration tests for FileSystem connector.

Tests the FileSystemConnector with real file operations,
testing document discovery, reading, and conversion.
"""

import pytest
from connectors.files import FileSystemConnector


@pytest.mark.integration
def test_filesystem_connector_basic(sample_documents):
    """Test FileSystem connector basic functionality."""
    connector = FileSystemConnector(
        path=str(sample_documents),
        include_patterns=[".*\\.md$"]
    )
    
    # Verify connector type
    assert connector.connector_type == "localFiles"
    
    # Test document reading
    documents = list(connector.reader.read_all_documents())
    assert len(documents) >= 2, "Should find at least 2 markdown documents"
    
    # Verify document structure (documents are dicts)
    for doc in documents:
        assert 'fileRelativePath' in doc
        assert 'fileFullPath' in doc
        assert 'content' in doc
        assert doc['content'] is not None


@pytest.mark.integration
def test_filesystem_connector_with_patterns(temp_workspace):
    """Test FileSystem connector with include/exclude patterns."""
    # Create test directory with multiple file types
    test_dir = temp_workspace / "pattern_test"
    test_dir.mkdir()
    
    (test_dir / "doc1.md").write_text("# Markdown 1")
    (test_dir / "doc2.md").write_text("# Markdown 2")
    (test_dir / "notes.txt").write_text("Plain text notes")
    (test_dir / "ignore.tmp").write_text("Temporary file")
    
    # Test with include pattern for only markdown
    connector = FileSystemConnector(
        path=str(test_dir),
        include_patterns=[r".*\.md$"],
        exclude_patterns=[r".*\.tmp$"]
    )
    
    documents = list(connector.reader.read_all_documents())
    
    # Should only find markdown files
    assert len(documents) == 2
    for doc in documents:
        assert doc['fileRelativePath'].endswith(".md")


@pytest.mark.integration
def test_filesystem_connector_conversion(sample_documents):
    """Test FileSystem connector document conversion."""
    connector = FileSystemConnector(
        path=str(sample_documents)
    )
    
    # Read and convert documents
    documents = list(connector.reader.read_all_documents())
    assert len(documents) > 0
    
    # Test conversion on first document
    result = connector.converter.convert(documents[0])
    
    # Converter returns a list of converted documents
    assert isinstance(result, list)
    assert len(result) > 0, "Should produce at least one converted document"
    
    first_converted = result[0]
    assert 'chunks' in first_converted
    assert len(first_converted['chunks']) > 0, "Should produce at least one chunk"
    
    # Verify chunk structure (chunks are also dicts)
    for chunk in first_converted['chunks']:
        assert isinstance(chunk, dict)
        assert 'indexedData' in chunk


@pytest.mark.integration
def test_filesystem_connector_empty_directory(temp_workspace):
    """Test FileSystem connector with empty directory."""
    empty_dir = temp_workspace / "empty"
    empty_dir.mkdir()
    
    connector = FileSystemConnector(path=str(empty_dir))
    
    documents = list(connector.reader.read_all_documents())
    assert len(documents) == 0, "Empty directory should yield no documents"


@pytest.mark.integration
def test_filesystem_connector_nested_directories(temp_workspace):
    """Test FileSystem connector with nested directory structure."""
    # Create nested structure
    base_dir = temp_workspace / "nested"
    sub1 = base_dir / "level1"
    sub2 = sub1 / "level2"
    
    sub2.mkdir(parents=True)
    
    (base_dir / "root.md").write_text("# Root Document")
    (sub1 / "level1.md").write_text("# Level 1 Document")
    (sub2 / "level2.md").write_text("# Level 2 Document")
    
    connector = FileSystemConnector(
        path=str(base_dir),
        include_patterns=[r".*\.md$"]
    )
    
    documents = list(connector.reader.read_all_documents())
    
    # Should find all 3 markdown files recursively
    assert len(documents) == 3

