"""Tests for information and documentation CLI commands.

These tests focus on realistic behaviors of:
- `indexed info docs` (docs function)
- `indexed info license` (license_terms function)
"""

import pytest
import typer
from typer.testing import CliRunner

from indexed.info import cli as info_cli


runner = CliRunner()


class TestDocsCommand:
    """Tests for the docs() helper command."""

    def test_docs_no_topic_opens_main_docs(self, monkeypatch):
        """Calling docs() without topic should open the main docs URL."""
        opened_urls: list[str] = []

        def fake_open(url):  # type: ignore[override]
            opened_urls.append(url)
            return True

        messages: list[str] = []

        def fake_success(msg: str) -> None:
            messages.append(msg)

        # Patch webbrowser.open and print_success
        monkeypatch.setattr(info_cli.webbrowser, "open", fake_open)
        monkeypatch.setattr(info_cli, "print_success", fake_success)

        result = runner.invoke(info_cli.app, ["docs"])

        assert result.exit_code == 0
        assert opened_urls == [info_cli.DOC_BASE_URL]
        assert any("Opening" in m for m in messages)

    @pytest.mark.parametrize(
        "topic,expected_suffix",
        [
            ("index", "/indexing"),
            ("config", "/configuration"),
            ("mcp", "/mcp"),
            ("confluence", "/indexing/connectors/confluence"),
            ("files", "/indexing/connectors/files"),
            ("jira", "/indexing/connectors/jira"),
        ],
    )
    def test_docs_valid_topic_routes_to_specific_page(
        self, topic: str, expected_suffix: str, monkeypatch
    ) -> None:
        """Docs with a known topic should open the corresponding page."""
        opened_urls: list[str] = []

        def fake_open(url):  # type: ignore[override]
            opened_urls.append(url)
            return True

        monkeypatch.setattr(info_cli.webbrowser, "open", fake_open)
        # Ignore success printing
        monkeypatch.setattr(info_cli, "print_success", lambda msg: None)

        result = runner.invoke(info_cli.app, ["docs", topic])

        assert result.exit_code == 0
        assert len(opened_urls) == 1
        assert opened_urls[0].startswith(info_cli.DOC_BASE_URL)
        assert opened_urls[0].endswith(expected_suffix)

    def test_docs_invalid_topic_shows_error_and_exits(self, monkeypatch):
        """Unknown topic should show a helpful error and exit with code 1."""
        errors: list[str] = []

        def fake_error(msg: str) -> None:
            errors.append(msg)

        monkeypatch.setattr(info_cli, "print_error", fake_error)

        result = runner.invoke(info_cli.app, ["docs", "unknown-topic"])

        assert result.exit_code == 1
        assert any("Unknown documentation topic" in e for e in errors)

    def test_docs_handles_browser_open_failure(self, monkeypatch):
        """If the browser fails to open, show a clear error and exit."""

        def failing_open(url):  # type: ignore[override]
            raise RuntimeError("Cannot open browser")

        errors: list[str] = []

        def fake_error(msg: str) -> None:
            errors.append(msg)

        monkeypatch.setattr(info_cli.webbrowser, "open", failing_open)
        monkeypatch.setattr(info_cli, "print_error", fake_error)

        result = runner.invoke(info_cli.app, ["docs", "index"])

        assert result.exit_code == 1
        assert any("Failed to open browser" in e for e in errors)


class TestLicenseCommand:
    """Tests for license_terms() behavior in common scenarios."""

    class _DummyPager:
        """Simple context manager to capture pager usage."""

        def __init__(self, called_flag: list[bool]):
            self._called_flag = called_flag

        def __enter__(self):
            self._called_flag[0] = True
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    def _patch_pager(self, monkeypatch):
        """Patch console.pager to avoid real paging and record usage."""
        called = [False]

        def fake_pager(*args, **kwargs):  # type: ignore[override]
            return self._DummyPager(called)

        monkeypatch.setattr(info_cli.console, "pager", fake_pager)
        return called

    def test_license_remote_success_uses_pager(self, monkeypatch):
        """When remote fetch works, license should be shown via pager."""

        # Fake successful HTTP response
        class FakeResponse:
            def __init__(self, text: str):
                self._text = text

            def read(self) -> bytes:
                return self._text.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(url, timeout=5):  # type: ignore[override]
            return FakeResponse("LICENSE CONTENT")

        monkeypatch.setattr(info_cli.urllib.request, "urlopen", fake_urlopen)
        pager_called = self._patch_pager(monkeypatch)

        # Should not raise
        info_cli.license_terms()

        assert pager_called[0] is True

    def test_license_remote_failure_falls_back_to_local(self, monkeypatch):
        """If remote fetch fails, it should fall back to local LICENSE file."""

        # First, make remote fetch fail
        def failing_urlopen(url, timeout=5):  # type: ignore[override]
            raise info_cli.urllib.error.URLError("network down")

        monkeypatch.setattr(info_cli.urllib.request, "urlopen", failing_urlopen)
        pager_called = self._patch_pager(monkeypatch)

        # Do not interfere with local LICENSE lookup; just ensure no crash
        info_cli.license_terms()

        assert pager_called[0] is True

    def test_license_failure_when_no_license_available(self, monkeypatch):
        """If neither remote nor local LICENSE can be read, exit with error."""

        # Remote fetch fails
        def failing_urlopen(url, timeout=5):  # type: ignore[override]
            raise info_cli.urllib.error.URLError("network down")

        monkeypatch.setattr(info_cli.urllib.request, "urlopen", failing_urlopen)

        # Simulate no package LICENSE and no filesystem LICENSE
        def fake_files(*args, **kwargs):  # type: ignore[override]
            raise FileNotFoundError("no package data")

        monkeypatch.setattr(info_cli.resources, "files", fake_files)

        # Force Path.exists() to always return False for LICENSE lookup
        class FakePath(info_cli.Path):  # type: ignore[misc]
            def exists(self) -> bool:  # type: ignore[override]
                return False

        monkeypatch.setattr(info_cli, "Path", FakePath)

        errors: list[str] = []

        def fake_error(msg: str) -> None:
            errors.append(msg)

        monkeypatch.setattr(info_cli, "print_error", fake_error)

        with pytest.raises(typer.Exit) as exc:
            info_cli.license_terms()

        assert exc.value.exit_code == 1
        assert any("LICENSE file not found" in e for e in errors)
