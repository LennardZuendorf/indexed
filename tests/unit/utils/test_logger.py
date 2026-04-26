"""Tests for utils.logger — single-sink Loguru architecture.

Covers bootstrap_logging, InterceptHandler stdlib capture, third-party logger
policy, status-sink subscriber API, file sink, and the no-raw-stderr property
that earlier suppress_core_output failed to deliver.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

from utils.logger import (
    THIRD_PARTY_LOGGERS,
    bootstrap_logging,
    emit_status,
    get_current_log_level,
    is_verbose_mode,
    subscribe_status,
    unsubscribe_status,
)


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset loguru + stdlib logging state between tests."""
    yield
    loguru_logger.remove()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    for name in THIRD_PARTY_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.setLevel(logging.NOTSET)
    logging.lastResort = logging.StreamHandler()  # restore default


class TestBootstrapBasics:
    def test_default_level_is_warning(self):
        bootstrap_logging("WARNING")
        assert get_current_log_level() == "WARNING"

    def test_normalizes_lowercase(self):
        bootstrap_logging("info")
        assert get_current_log_level() == "INFO"

    def test_reconfigures_idempotently(self):
        bootstrap_logging("WARNING")
        bootstrap_logging("DEBUG")
        # Loguru should have a single sink replacement, not stacked
        assert get_current_log_level() == "DEBUG"

    def test_verbose_mode_detection(self):
        bootstrap_logging("INFO")
        assert is_verbose_mode() is True
        bootstrap_logging("DEBUG")
        assert is_verbose_mode() is True
        bootstrap_logging("WARNING")
        assert is_verbose_mode() is False
        bootstrap_logging("ERROR")
        assert is_verbose_mode() is False


class TestStdlibCapture:
    def test_loguru_warning_appears(self, capsys):
        bootstrap_logging("WARNING")
        loguru_logger.warning("from loguru")
        captured = capsys.readouterr()
        assert "from loguru" in (captured.out + captured.err)

    def test_loguru_debug_appears_when_debug(self, capsys):
        bootstrap_logging("DEBUG", debug=True)
        loguru_logger.debug("debug msg")
        captured = capsys.readouterr()
        assert "debug msg" in (captured.out + captured.err)

    def test_stdlib_root_logging_routed_via_intercept(self, capsys):
        bootstrap_logging("WARNING")
        logging.getLogger().error("from root stdlib")
        captured = capsys.readouterr()
        assert "from root stdlib" in (captured.out + captured.err)


class TestThirdPartyPolicy:
    def test_docling_error_silenced_at_default(self, capsys):
        bootstrap_logging("WARNING")
        logging.getLogger("docling.datamodel.document").error(
            "Input document README.rst with format None does not match"
        )
        captured = capsys.readouterr()
        assert "does not match" not in captured.out
        assert "does not match" not in captured.err

    def test_docling_error_visible_at_debug(self, capsys):
        bootstrap_logging("DEBUG", debug=True)
        logging.getLogger("docling.datamodel.document").error(
            "noise visible in debug"
        )
        captured = capsys.readouterr()
        assert "noise visible in debug" in (captured.out + captured.err)

    def test_transformers_info_silenced_at_default(self, capsys):
        bootstrap_logging("WARNING")
        logging.getLogger("transformers").info("loading shards")
        captured = capsys.readouterr()
        assert "loading shards" not in (captured.out + captured.err)

    def test_unknown_noisy_logger_does_not_leak_raw(self, capsys):
        """A logger NOT in policy table should not produce raw stderr leak.

        Even at default verbosity, since lastResort is dead. Record may surface
        via Rich rendering at WARNING+ but never as raw stderr garbage.
        """
        bootstrap_logging("WARNING")
        # No NullHandler attached; relies on lastResort=None defense
        logging.getLogger("brand_new_unlisted_lib").error("y")
        captured = capsys.readouterr()
        # Either silenced or rendered through loguru — not raw "ERROR:..." stderr
        assert "ERROR:brand_new_unlisted_lib" not in captured.err
        assert "ERROR:root" not in captured.err

    def test_lastresort_is_killed(self):
        bootstrap_logging("WARNING")
        assert logging.lastResort is None


class TestStatusSink:
    def test_emit_and_subscribe(self):
        bootstrap_logging("WARNING")
        received = []
        token = subscribe_status(received.append)
        emit_status("step 3 of 10")
        unsubscribe_status(token)
        assert "step 3 of 10" in received

    def test_unsubscribe_stops_callbacks(self):
        bootstrap_logging("WARNING")
        received = []
        token = subscribe_status(received.append)
        unsubscribe_status(token)
        emit_status("after unsubscribe")
        assert received == []

    def test_quiet_disables_status(self):
        bootstrap_logging("ERROR", quiet=True)
        received = []
        token = subscribe_status(received.append)
        emit_status("should not arrive")
        unsubscribe_status(token)
        assert received == []

    def test_multiple_subscribers_each_receive(self):
        bootstrap_logging("WARNING")
        a, b = [], []
        ta = subscribe_status(a.append)
        tb = subscribe_status(b.append)
        emit_status("hello")
        unsubscribe_status(ta)
        unsubscribe_status(tb)
        assert "hello" in a
        assert "hello" in b

    def test_unsubscribe_one_leaves_others(self):
        bootstrap_logging("WARNING")
        a, b = [], []
        ta = subscribe_status(a.append)
        tb = subscribe_status(b.append)
        unsubscribe_status(ta)
        emit_status("only b")
        unsubscribe_status(tb)
        assert a == []
        assert "only b" in b


class TestFileSink:
    def test_debug_creates_file(self, tmp_path: Path):
        bootstrap_logging("DEBUG", debug=True, log_dir=tmp_path)
        loguru_logger.debug("file content marker")
        # File rotation: at least one file should exist with the message
        files = list(tmp_path.glob("indexed-*.log"))
        assert files, f"expected log file in {tmp_path}, got {list(tmp_path.iterdir())}"
        contents = "".join(f.read_text() for f in files)
        assert "file content marker" in contents

    def test_no_file_at_default(self, tmp_path: Path):
        bootstrap_logging("WARNING", log_dir=tmp_path)
        loguru_logger.warning("no file")
        assert list(tmp_path.glob("indexed-*.log")) == []


class TestThemeStylesInjection:
    def test_default_styles_render_without_rich(self, capsys):
        """Without theme_styles or rich_console, sink renders plain text."""
        bootstrap_logging("WARNING")
        loguru_logger.warning("plain")
        captured = capsys.readouterr()
        assert "plain" in (captured.out + captured.err)

    def test_custom_theme_styles_accepted(self, capsys):
        """Sink accepts a theme_styles dict without error."""
        styles = {
            "WARNING": "yellow",
            "ERROR": "bold red",
            "INFO": "cyan",
            "DEBUG": "dim",
        }
        bootstrap_logging("WARNING", theme_styles=styles)
        loguru_logger.warning("themed")
        captured = capsys.readouterr()
        assert "themed" in (captured.out + captured.err)
