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
