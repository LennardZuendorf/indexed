"""Basic tests for FileSystem connector."""

import tempfile
import pytest
from connectors.files.connector import FileSystemConnector
from connectors.files.schema import LocalFilesConfig
from connectors.files.files_document_reader import FilesDocumentReader


pytestmark = pytest.mark.connectors  # Mark all tests in this file as connector tests


def test_filesystem_connector_init():
    """Test FileSystemConnector initialization with minimal config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        connector = FileSystemConnector(path=tmpdir)

        assert connector.connector_type == "localFiles"
        assert isinstance(connector.reader, FilesDocumentReader)
        assert tmpdir in str(connector)


def test_filesystem_connector_with_patterns():
    """Test FileSystemConnector initialization with include/exclude patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        connector = FileSystemConnector(
            path=tmpdir,
            include_patterns=[r".*\.md$", r".*\.txt$"],
            exclude_patterns=[r".*test.*", r".*/node_modules/.*"],
            fail_fast=True,
        )

        assert isinstance(connector.reader, FilesDocumentReader)
        assert connector.connector_type == "localFiles"
        assert r".*\.md$" in connector._include_patterns
        assert r".*test.*" in connector._exclude_patterns
        assert connector._fail_fast is True


def test_filesystem_connector_invalid_path():
    """Test FileSystemConnector raises error for non-existent path."""
    with pytest.raises(ValueError, match="Path does not exist"):
        FileSystemConnector(path="/non/existent/path")


def test_filesystem_connector_config_spec():
    """Test FileSystemConnector.config_spec() returns correct specification."""
    spec = FileSystemConnector.config_spec()

    # Verify path is required
    assert spec["path"]["type"] == "str"
    assert spec["path"]["required"] is True
    assert spec["path"]["secret"] is False

    # Verify include_patterns is optional with default
    assert spec["include_patterns"]["type"] == "list"
    assert spec["include_patterns"]["required"] is False
    assert spec["include_patterns"]["default"] == [".*"]

    # Verify exclude_patterns is optional with default
    assert spec["exclude_patterns"]["type"] == "list"
    assert spec["exclude_patterns"]["required"] is False
    assert spec["exclude_patterns"]["default"] == []

    # Verify fail_fast is optional with default
    assert spec["fail_fast"]["type"] == "bool"
    assert spec["fail_fast"]["required"] is False
    assert spec["fail_fast"]["default"] is False


def test_filesystem_connector_repr():
    """Test FileSystemConnector string representation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        connector = FileSystemConnector(
            path=tmpdir, include_patterns=[r".*\.md$"], exclude_patterns=[r".*test.*"]
        )

        repr_str = str(connector)
        assert "FileSystemConnector" in repr_str
        assert tmpdir in repr_str
        # Note: backslashes are escaped in the string representation
        assert r".*\.md$" in repr_str or ".*\\\\.md$" in repr_str
        assert r".*test.*" in repr_str


def test_filesystem_connector_properties():
    """Test FileSystemConnector reader and converter properties."""
    with tempfile.TemporaryDirectory() as tmpdir:
        connector = FileSystemConnector(path=tmpdir)

        # Test reader property
        reader = connector.reader
        assert isinstance(reader, FilesDocumentReader)
        assert reader is connector._reader  # Same instance

        # Test converter property
        converter = connector.converter
        assert converter is connector._converter  # Same instance

        # Test connector_type property
        assert connector.connector_type == "localFiles"
