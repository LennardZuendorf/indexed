"""End-to-end regression: no raw stderr leakage from third-party libs.

This is the test that would have caught the original bug. Earlier
``suppress_core_output`` patched the wrong place (filter on root logger which
Python's logging propagation never consults during ``callHandlers``). With the
single-sink ``utils.logger`` architecture, leakage is killed at multiple
layers — see ``docs/plans/2026-04-25-001-refactor-cli-logging-pipeline-plan.md``.

Covers:
- Synthetic docling-style ERROR at default verbosity → no stderr.
- Same record at ``--debug`` → reaches the captured loguru output (Rich-rendered).
- ``ParsingModule.parse`` over a directory containing .rst, .md, .txt fixtures
  at default verbosity → no docling format-mismatch lines anywhere.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

from utils import THIRD_PARTY_LOGGERS, bootstrap_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    loguru_logger.remove()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    for name in THIRD_PARTY_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.setLevel(logging.NOTSET)
    logging.lastResort = logging.StreamHandler()


class TestNoStderrLeakAtDefault:
    def test_docling_error_silenced(self, capsys):
        bootstrap_logging("WARNING")
        logging.getLogger("docling.datamodel.document").error(
            "Input document README.rst with format None does not match any allowed format"
        )
        captured = capsys.readouterr()
        assert "does not match any allowed format" not in captured.out
        assert "does not match any allowed format" not in captured.err
        assert "Input document" not in captured.err

    def test_unlisted_third_party_error_does_not_leak_raw(self, capsys):
        """A logger NOT in policy table cannot produce raw 'ERROR:name' stderr.

        It may surface via the Rich-rendered loguru sink (which is fine — that's
        intentional visibility), but it must never appear as the raw stdlib
        format ``ERROR:logger.name:message`` on stderr.
        """
        bootstrap_logging("WARNING")
        logging.getLogger("brand_new_unlisted_lib").error("y")
        captured = capsys.readouterr()
        assert "ERROR:brand_new_unlisted_lib" not in captured.err

    def test_lastresort_is_killed(self):
        bootstrap_logging("WARNING")
        assert logging.lastResort is None

    def test_warnings_warn_does_not_leak(self, capsys):
        """Python's warnings.warn must be captured through logging.

        Libraries like PIL, multiprocessing/loky, and pptx call warnings.warn
        which bypasses stdlib logging by default and writes directly to stderr.
        bootstrap_logging calls logging.captureWarnings(True) to route these
        through the InterceptHandler.
        """
        import warnings as _warnings

        bootstrap_logging("WARNING")
        _warnings.warn("ImageWarning: simulated PIL palette message", UserWarning)
        captured = capsys.readouterr()
        # py.warnings is in the policy table at ERROR — UserWarning hits at
        # WARNING, so it's silenced at default verbosity.
        assert "simulated PIL palette message" not in (captured.out + captured.err)


class TestDocingVisibleAtDebug:
    def test_docling_record_visible_at_debug(self, capsys):
        bootstrap_logging("DEBUG", debug=True)
        logging.getLogger("docling.datamodel.document").error(
            "intentional debug-mode visibility"
        )
        captured = capsys.readouterr()
        assert "intentional debug-mode visibility" in (captured.out + captured.err)


class TestParsingModuleNoLeakOnRstFixture:
    """End-to-end through ParsingModule with a mixed-extension directory."""

    def _make_fixture(self, tmp_path: Path) -> Path:
        (tmp_path / "README.rst").write_text(
            "Title\n=====\n\nA reST paragraph.\n"
        )
        (tmp_path / "doc.md").write_text("# Heading\n\nMarkdown body.\n")
        (tmp_path / "notes.txt").write_text("plain text content")
        return tmp_path

    def test_no_docling_noise_for_rst(self, capsys, tmp_path):
        from parsing import ParsingModule

        bootstrap_logging("WARNING")
        fixture = self._make_fixture(tmp_path)
        module = ParsingModule(ocr=False, table_structure=False)

        for f in sorted(fixture.iterdir()):
            module.parse(f)

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "does not match any allowed format" not in combined
        assert "Input document README.rst" not in combined
        assert "Input document notes.txt" not in combined
