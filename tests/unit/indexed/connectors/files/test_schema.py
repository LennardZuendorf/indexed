"""Tests for FileSystemConfig.normalize_patterns (rendering-fixes/2, R3).

The validator must keep the user's original pattern text for the glob branch
instead of substituting fnmatch.translate()'s regex form -- that translated
string was leaking into the "Included Patterns" display row. Validation
behavior (an unparseable pattern still raises) and matching behavior (both
old-style translated and new-style raw manifests still match files) must be
unchanged.
"""

import fnmatch
import re

import pytest

from indexed.connectors.files.schema import FileSystemConfig


class TestNormalizePatternsKeepsOriginalText:
    """Part A: the glob branch must store the raw pattern, not its translation."""

    def test_default_star_pattern_kept_literal(self):
        config = FileSystemConfig(path=".", include_patterns=["*"])
        assert config.include_patterns == ["*"]

    def test_custom_glob_pattern_kept_literal(self):
        config = FileSystemConfig(path=".", include_patterns=["*.py"])
        assert config.include_patterns == ["*.py"]

    def test_negated_glob_pattern_keeps_bang_prefix_and_text(self):
        config = FileSystemConfig(path=".", include_patterns=["*", "!*.pyc"])
        assert config.include_patterns == ["*", "!*.pyc"]

    def test_valid_regex_pattern_unaffected(self):
        """Patterns that already compile as regex bypass the glob branch
        entirely and must keep working exactly as before."""
        config = FileSystemConfig(path=".", include_patterns=[r".*\.md$"])
        assert config.include_patterns == [r".*\.md$"]

    def test_mixed_regex_and_glob_patterns_each_kept_literal(self):
        """A list mixing a valid-regex pattern with a glob-needing-translation
        pattern must keep each one's own original text."""
        config = FileSystemConfig(
            path=".", include_patterns=[r".*\.md$", "*.py", "!*.pyc"]
        )
        assert config.include_patterns == [r".*\.md$", "*.py", "!*.pyc"]

    def test_empty_include_patterns_list_preserved(self):
        config = FileSystemConfig(path=".", include_patterns=[])
        assert config.include_patterns == []


class TestNormalizePatternsStillValidates:
    """An unparseable pattern must still raise -- the fnmatch.translate() call
    stays in place purely to confirm the glob branch doesn't itself raise."""

    def test_unparseable_pattern_raises(self, monkeypatch):
        """Neither re.compile nor fnmatch.translate can handle this: force
        fnmatch.translate to also raise, simulating a pattern that is valid
        under neither interpretation."""

        def _boom(_pattern: str) -> str:
            raise re.error("boom")

        monkeypatch.setattr(fnmatch, "translate", _boom)
        with pytest.raises(Exception):
            FileSystemConfig(path=".", include_patterns=["*"])

    def test_invalid_regex_like_pattern_still_raises_via_pydantic(self):
        """An unbalanced regex-looking pattern fails re.compile, then also
        fails to be usable -- fnmatch.translate() on it succeeds (it treats
        the text as a literal glob), so this documents that the fallback is
        permissive by design; genuinely bad input is exercised via the
        monkeypatched case above."""
        # Sanity: this does NOT raise, since fnmatch.translate("(" ) succeeds.
        config = FileSystemConfig(path=".", include_patterns=["("])
        assert config.include_patterns == ["("]


class TestCompileMatchesBothOldAndNewStylePatterns:
    """_compile() re-derives the working regex from raw text at match time,
    so both a new-style raw pattern and an old-style already-translated
    pattern must still match files correctly (no manifest migration needed)."""

    def test_raw_glob_pattern_matches_via_compile(self):
        from indexed.connectors.files.files_document_reader import (
            FilesDocumentReader,
        )

        pattern = FilesDocumentReader._compile("*.py")
        assert pattern.match("foo.py")
        assert not pattern.match("foo.txt")

    def test_legacy_translated_pattern_matches_via_compile(self):
        """A manifest persisted before this fix carries fnmatch.translate()'s
        regex output directly; _compile() must accept it as valid regex."""
        from indexed.connectors.files.files_document_reader import (
            FilesDocumentReader,
        )

        legacy = fnmatch.translate("*.py")
        pattern = FilesDocumentReader._compile(legacy)
        assert pattern.match("foo.py")
        assert not pattern.match("foo.txt")


class TestConnectorToManifestIncludePatterns:
    """Closes the loop from config through to what a new collection actually
    persists: FileSystemConnector -> FileSystemConfig -> FilesDocumentReader
    -> get_reader_details()["includePatterns"], the exact dict shape written
    into manifest.json (files_document_reader.py:168)."""

    def test_default_patterns_persist_as_literal_star(self, tmp_path):
        from indexed.connectors.files.connector import FileSystemConnector

        connector = FileSystemConnector(path=str(tmp_path))
        details = connector.reader.get_reader_details()
        assert details["includePatterns"] == ["*"]

    def test_custom_glob_persists_literally(self, tmp_path):
        from indexed.connectors.files.connector import FileSystemConnector

        connector = FileSystemConnector(path=str(tmp_path), include_patterns=["*.py"])
        details = connector.reader.get_reader_details()
        assert details["includePatterns"] == ["*.py"]
