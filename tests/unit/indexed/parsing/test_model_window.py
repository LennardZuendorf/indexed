"""Tests for parsing._model_window — tokenizer acquisition and degradation.

Locks the clean-machine first-run contract: the tokenizer is downloaded at
most once, a failed load is reported exactly one line (never a traceback per
chunk, never an internal bug id), and offline runs never spend time on a
doomed Hub request.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from loguru import logger

from indexed.parsing import _model_window as mw


class _FakeTokenizer:
    """Minimal stand-in for a PreTrainedTokenizerFast."""

    def __init__(self, tokens_per_char: int = 1) -> None:
        self.tokens_per_char = tokens_per_char

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(range(len(text) * self.tokens_per_char))


def _install_transformers(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    """Put a fake ``transformers.AutoTokenizer`` in front of the real import."""
    module = types.ModuleType("transformers")
    module.AutoTokenizer = types.SimpleNamespace(from_pretrained=handler)
    monkeypatch.setitem(sys.modules, "transformers", module)


class _RacingTransformers(types.ModuleType):
    """A fake ``transformers`` whose ``AutoTokenizer`` import fails first.

    Reproduces the half-initialised module a thread sees when another thread is
    first-importing ``transformers`` (issue #335): the attribute is missing on
    the first ``failures`` accesses and present afterwards.
    """

    def __init__(self, failures: int) -> None:
        super().__init__("transformers")
        self.failures = failures
        self.attempts = 0

    def __getattr__(self, name: str) -> Any:
        if name != "AutoTokenizer":
            raise AttributeError(name)
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ImportError("cannot import name 'AutoTokenizer' from 'transformers'")
        return types.SimpleNamespace(from_pretrained=lambda *a, **kw: _FakeTokenizer())


def _install_racing_transformers(
    monkeypatch: pytest.MonkeyPatch, *, failures: int
) -> _RacingTransformers:
    module = _RacingTransformers(failures)
    monkeypatch.setitem(sys.modules, "transformers", module)
    # The retry's settle delay is real time; the fake module needs none of it.
    monkeypatch.setattr(mw, "_IMPORT_RETRY_SECONDS", 0, raising=False)
    return module


def _install_fake_docling(monkeypatch: pytest.MonkeyPatch) -> type:
    """Install a fake docling_core chunker package; return the fallback class."""

    class HierarchicalChunker:
        pass

    class HybridChunker:
        def __init__(self, tokenizer: Any = None) -> None:
            self.tokenizer = tokenizer

    class HuggingFaceTokenizer:
        def __init__(self, tokenizer: Any = None, max_tokens: int = 0) -> None:
            self.tokenizer = tokenizer
            self.max_tokens = max_tokens

    modules = {
        name: types.ModuleType(name)
        for name in (
            "docling_core",
            "docling_core.transforms",
            "docling_core.transforms.chunker",
            "docling_core.transforms.chunker.tokenizer",
            "docling_core.transforms.chunker.tokenizer.huggingface",
        )
    }
    chunker = modules["docling_core.transforms.chunker"]
    setattr(chunker, "HybridChunker", HybridChunker)
    setattr(chunker, "HierarchicalChunker", HierarchicalChunker)
    setattr(
        modules["docling_core.transforms.chunker.tokenizer.huggingface"],
        "HuggingFaceTokenizer",
        HuggingFaceTokenizer,
    )
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return HierarchicalChunker


@pytest.fixture(autouse=True)
def _fresh_tokenizer_cache(monkeypatch: pytest.MonkeyPatch):
    """Each test starts from an untried tokenizer, with no offline override."""
    for var in mw._OFFLINE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    mw._get_tokenizer.cache_clear()
    yield
    mw._get_tokenizer.cache_clear()


@pytest.fixture
def logs() -> Any:
    """Formatted loguru records for one test (the default sink is untouched)."""
    records: list[Any] = []
    handler_id = logger.add(records.append, level="DEBUG")
    capture = types.SimpleNamespace(
        at=lambda level: [str(r) for r in records if r.record["level"].name == level]
    )
    yield capture
    logger.remove(handler_id)


def _raiser(name: str, **kwargs: Any) -> Any:
    raise RuntimeError("cannot load tokenizer")


class TestTokenizerLoad:
    def test_cached_tokenizer_loads_offline_without_download(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        calls: list[dict[str, Any]] = []

        def handler(name: str, **kwargs: Any) -> _FakeTokenizer:
            calls.append(kwargs)
            return _FakeTokenizer(tokens_per_char=2)

        _install_transformers(monkeypatch, handler)

        assert mw.count_tokens("abc") == 6
        assert calls == [{"local_files_only": True}]
        assert logs.at("WARNING") == []

    def test_clean_cache_downloads_tokenizer_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        calls: list[dict[str, Any]] = []

        def handler(name: str, **kwargs: Any) -> _FakeTokenizer:
            calls.append(kwargs)
            if kwargs.get("local_files_only"):
                raise OSError("not in the local cache")
            return _FakeTokenizer()

        _install_transformers(monkeypatch, handler)

        for _ in range(5):
            assert mw.count_tokens("ab") == 2
        # The download happened once, not once per chunk.
        assert calls == [{"local_files_only": True}, {}]
        # A successful first-run fetch is not a warning.
        assert logs.at("WARNING") == []

    def test_offline_environment_skips_the_download(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        calls: list[dict[str, Any]] = []

        def handler(name: str, **kwargs: Any) -> _FakeTokenizer:
            calls.append(kwargs)
            raise OSError("not in the local cache")

        _install_transformers(monkeypatch, handler)

        assert mw.count_tokens("abcdef") == len("abcdef") // 3 + 1
        assert calls == [{"local_files_only": True}]
        assert len(logs.at("WARNING")) == 1


class TestConcurrentFirstImport:
    """Issue #335: a first import racing another thread must not stick."""

    def test_import_error_once_is_retried_and_the_tokenizer_cached(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        """Red before the fix: ``None`` was cached after the first ImportError."""
        module = _install_racing_transformers(monkeypatch, failures=1)

        assert mw._get_tokenizer() is not None
        # One failure, one retry — and the success is what the cache keeps.
        assert module.attempts == 2
        assert mw.count_tokens("abc") == 3
        assert module.attempts == 2
        assert logs.at("WARNING") == []

    def test_persistent_import_error_is_not_blamed_on_the_model_cache(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        """A broken ``transformers`` keeps the WARNING but not the init advice."""
        module = _install_racing_transformers(monkeypatch, failures=99)

        assert mw.count_tokens("abcdef") == len("abcdef") // 3 + 1
        # Exactly one retry, then give up (the failure is still cached once).
        assert module.attempts == 2
        warnings = logs.at("WARNING")
        assert len(warnings) == 1, warnings
        assert "character-count estimate" in warnings[0]
        # The model is on disk; re-running `indexed init` cannot fix the import.
        assert "indexed init" not in warnings[0]
        assert any("AutoTokenizer" in record for record in logs.at("DEBUG"))


class TestDegradation:
    def test_unavailable_tokenizer_warns_once_without_traceback(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        _install_transformers(monkeypatch, _raiser)

        # 50 chunk-size checks in one run (a clean first run does far more).
        for _ in range(50):
            assert mw.count_tokens("some chunk text") == len("some chunk text") // 3 + 1
        assert mw.count_tokens("") == 0

        warnings = logs.at("WARNING")
        assert len(warnings) == 1, warnings
        message = warnings[0]
        assert "character-count estimate" in message
        assert "indexed init" in message
        # No internal bug ids or stack dumps in user-facing output.
        assert "bug A" not in message
        assert "Traceback" not in message
        # The full cause stays available one level down.
        assert any("cannot load tokenizer" in r for r in logs.at("DEBUG"))

    def test_markdown_chunker_falls_back_silently(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        _install_transformers(monkeypatch, _raiser)
        fallback = _install_fake_docling(monkeypatch)

        chunker = mw.get_markdown_chunker()

        assert isinstance(chunker, fallback)
        # One warning in total (the tokenizer), not one per chunker build.
        assert len(logs.at("WARNING")) == 1

    def test_markdown_chunker_is_token_aware_when_tokenizer_loads(
        self, monkeypatch: pytest.MonkeyPatch, logs: Any
    ) -> None:
        _install_transformers(monkeypatch, lambda name, **kwargs: _FakeTokenizer())
        _install_fake_docling(monkeypatch)

        chunker = mw.get_markdown_chunker()

        assert chunker.tokenizer.max_tokens == mw.DEFAULT_MODEL_MAX_SEQ_LENGTH
        assert logs.at("WARNING") == []
