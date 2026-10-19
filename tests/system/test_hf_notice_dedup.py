"""#211 regression: the HuggingFace Hub notice renders EXACTLY once.

The issue is not cosmetic. Two independent sinks printed the same notice:

1. ``huggingface_hub.utils.logging`` runs ``_configure_library_root_logger()``
   at import — it attaches a bare ``StreamHandler`` to the ``huggingface_hub``
   logger and sets that logger to WARNING. Every ML import in indexed is lazy,
   so this happens *after* ``bootstrap_logging``: the raw handler writes
   unformatted lines straight to stderr (bypassing ``--quiet``), and the level
   reset also overrides ``THIRD_PARTY_LOGGERS``.
2. The same record still propagates into Loguru's console sink, which renders
   ``WARNING  | Warning: ...`` (the server already prefixed the message).

So one notice rendered twice at default verbosity, and the raw copy survived
``--quiet``. These tests assert the rendered notice COUNT (and the line shape),
not substring presence — the duplicate *is* the bug, so presence-only
assertions cannot catch its return.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

from indexed.core.v1.engine.indexes.embeddings.model_manager import ensure_model
from indexed.utils import THIRD_PARTY_LOGGERS, bootstrap_logging

MODEL = "all-MiniLM-L6-v2"

#: Verbatim X-HF-Warning payload (already carries HF's own "Warning: " prefix).
NOTICE = (
    "Warning: You are sending unauthenticated requests to the HF Hub. "
    "Please set a HF_TOKEN to enable higher rate limits and faster downloads."
)
#: The part every rendering of the notice contains — counted, never mere presence.
NOTICE_BODY = "You are sending unauthenticated requests"

#: The one acceptable rendering: our level column, then the de-prefixed message.
RENDERED_LINE = re.compile(r"^WARNING\s+\| You are sending unauthenticated requests")


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    loguru_logger.remove()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    for name in (*THIRD_PARTY_LOGGERS, "huggingface_hub.utils._http"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.setLevel(logging.NOTSET)
    logging.lastResort = logging.StreamHandler()


def _hf_reconfigures_its_logger() -> None:
    """Apply exactly what ``import huggingface_hub`` does to logging.

    Called between ``bootstrap_logging`` and ``ensure_model`` to stand in for
    the lazy import that happens inside ``ensure_model`` in a real CLI run.
    Calling the library's own hook (instead of hand-rolling a StreamHandler)
    keeps the emulation faithful across HF versions.
    """
    from huggingface_hub.utils.logging import _configure_library_root_logger

    _configure_library_root_logger()


def _snapshot_with_weights(tmp_path: Path) -> Path:
    """A downloaded-looking snapshot directory (outside the cache)."""
    snap = tmp_path / "downloaded-snapshot"
    snap.mkdir()
    (snap / "config.json").write_text('{"model_type": "bert"}')
    (snap / "model.safetensors").write_bytes(b"\x00" * 128)
    return snap


def _seed_cached_model(cache_root: Path) -> None:
    """Populate a HF cache the weights-aware predicate accepts."""
    repo = cache_root / "models--sentence-transformers--all-MiniLM-L6-v2"
    (repo / "blobs").mkdir(parents=True)
    (repo / "refs").mkdir(parents=True)
    snap = repo / "snapshots" / "deadbeef"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")
    (snap / "model.safetensors").write_bytes(b"\x00" * 256)
    (repo / "refs" / "main").write_text("deadbeef")


def _fake_hub_call(monkeypatch, snapshot: Path, calls: list[str]) -> None:
    """Stand in for ``snapshot_download``, emitting the notice the way HF does.

    HF's ``_warn_on_warning_headers`` logs the X-HF-Warning payload through
    ``huggingface_hub.utils._http``; the same logger name keeps the record on
    the real parent-child hierarchy (and therefore under the parent's handler).
    """
    import huggingface_hub

    def fake_snapshot_download(*, repo_id: str, **_: object) -> str:
        calls.append(repo_id)
        logging.getLogger("huggingface_hub.utils._http").warning(NOTICE)
        return str(snapshot)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)


class TestNoticeCount:
    def test_default_warning_renders_exactly_one_notice(
        self, capsys, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
        snapshot = _snapshot_with_weights(tmp_path)
        calls: list[str] = []
        _fake_hub_call(monkeypatch, snapshot, calls)

        bootstrap_logging("WARNING")
        # The lazy `from huggingface_hub import ...` inside ensure_model runs
        # here in a real run, re-attaching HF's own StreamHandler.
        _hf_reconfigures_its_logger()

        ensure_model(MODEL, force=True)

        err = capsys.readouterr().err
        assert calls, "the download seam was never reached"
        assert err.count(NOTICE_BODY) == 1, f"expected one notice, got:\n{err}"

        rendered = [line for line in err.splitlines() if NOTICE_BODY in line]
        assert len(rendered) == 1
        assert RENDERED_LINE.match(rendered[0]), rendered[0]
        # The redundant server-side prefix must not survive into the output.
        assert "Warning: You are sending" not in err

    def test_quiet_renders_no_notice(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
        snapshot = _snapshot_with_weights(tmp_path)
        calls: list[str] = []
        _fake_hub_call(monkeypatch, snapshot, calls)

        bootstrap_logging("ERROR", quiet=True)
        _hf_reconfigures_its_logger()

        ensure_model(MODEL, force=True)

        err = capsys.readouterr().err
        assert calls, "the download seam was never reached"
        assert NOTICE_BODY not in err, f"--quiet must silence the notice, got:\n{err}"

    def test_cached_model_renders_no_notice(self, capsys, tmp_path, monkeypatch):
        cache_root = tmp_path / "hub"
        monkeypatch.setenv("HF_HUB_CACHE", str(cache_root))
        _seed_cached_model(cache_root)
        calls: list[str] = []
        _fake_hub_call(monkeypatch, _snapshot_with_weights(tmp_path), calls)

        bootstrap_logging("WARNING")

        ensure_model(MODEL)

        err = capsys.readouterr().err
        assert calls == [], "a cached model must not call the Hub"
        assert NOTICE_BODY not in err
