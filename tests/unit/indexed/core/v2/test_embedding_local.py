"""Unit tests for the core.v2 native embedding factory + probe (core-v2/2b).

Two tiers:

* Model-free unit tests monkeypatch the integration's ``HuggingFaceEmbedding``
  with a kwarg-capturing fake, so the offline/cache wiring (explicit
  ``model_name``/``normalize``, the shared HF-hub ``cache_folder``, and
  ``local_files_only`` iff cached) is locked whether or not the real model is
  present. IS_TESTING is NOT usable here: ``HuggingFaceEmbedding`` is built
  directly (not resolved through ``Settings``), so llama-index's mock-embedding
  path never triggers — the fake-class monkeypatch is used instead.
* Real tests gate on ``model_available()``: 384-dim, unit norm, the dimension
  probe, no-network-when-cached (socket guard), and 1:1 cosine parity vs v1.
"""

from __future__ import annotations

import math
import socket
from pathlib import Path

import pytest

from indexed.core.v2.config_models import CoreV2EmbeddingConfig
from indexed.core.v2.embedding import local
from tests.conftest import model_available

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _hub_snapshot(cache: Path, revision: str) -> Path:
    """HF-hub snapshot dir for MODEL at ``revision``; creates it if absent."""
    snap = cache / f"models--{MODEL.replace('/', '--')}" / "snapshots" / revision
    snap.mkdir(parents=True)
    return snap


class _FakeEmbed:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def get_text_embedding(self, text: str) -> list[float]:
        return [0.0] * 384


def _patch_fake(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace the integration class with a kwarg-capturing fake.

    ``build_embed_model`` does ``from llama_index.embeddings.huggingface import
    HuggingFaceEmbedding`` at call time, so patching the module attribute is
    picked up without importing torch.
    """
    import llama_index.embeddings.huggingface as hf

    captured: dict[str, object] = {}

    def factory(**kwargs: object) -> _FakeEmbed:
        captured.clear()
        captured.update(kwargs)
        return _FakeEmbed(**kwargs)

    monkeypatch.setattr(hf, "HuggingFaceEmbedding", factory)
    return captured


# --------------------------------------------------------------------------
# Model-free wiring tests
# --------------------------------------------------------------------------


def test_build_passes_explicit_model_and_normalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_fake(monkeypatch)
    monkeypatch.setattr(local, "_is_model_cached", lambda name: True)

    local.build_embed_model(CoreV2EmbeddingConfig())

    assert captured["model_name"] == MODEL  # explicit — not the integration default
    assert captured["embed_batch_size"] == 32
    assert captured["normalize"] is True


def test_build_uses_shared_hf_hub_cache_not_llamaindex_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_fake(monkeypatch)
    monkeypatch.setattr(local, "_is_model_cached", lambda name: True)

    local.build_embed_model(CoreV2EmbeddingConfig())

    assert captured["cache_folder"] == str(local._hf_hub_cache_dir())
    # Guard the landmine: never LlamaIndex's own cache dir.
    assert "llama_index" not in str(captured["cache_folder"])


def test_build_local_files_only_tracks_cache_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cached → local_files_only True (forbids the network etag probe).
    captured = _patch_fake(monkeypatch)
    monkeypatch.setattr(local, "_is_model_cached", lambda name: True)
    local.build_embed_model(CoreV2EmbeddingConfig())
    assert captured["local_files_only"] is True

    # Not cached → False (the default), so a first run may still download.
    captured2 = _patch_fake(monkeypatch)
    monkeypatch.setattr(local, "_is_model_cached", lambda name: False)
    local.build_embed_model(CoreV2EmbeddingConfig())
    assert captured2["local_files_only"] is False


def test_build_goes_online_when_cache_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Download residue (config-only) must stay online so hub can resume it."""
    captured = _patch_fake(monkeypatch)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    (_hub_snapshot(tmp_path, "deadbeef") / "config.json").write_text("{}")

    local.build_embed_model(CoreV2EmbeddingConfig())

    assert captured["local_files_only"] is False
    assert captured["cache_folder"] == str(tmp_path)


def test_build_model_failure_is_actionable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A failed model load surfaces a remedy, not transformers internals."""
    import llama_index.embeddings.huggingface as hf

    from indexed.core.errors import CoreV2Error

    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))

    def broken(**kwargs: object) -> None:
        raise OSError(f"{MODEL}: no pytorch_model.bin or model.safetensors")

    monkeypatch.setattr(hf, "HuggingFaceEmbedding", broken)

    with pytest.raises(CoreV2Error) as excinfo:
        local.build_embed_model(CoreV2EmbeddingConfig())

    message = str(excinfo.value)
    assert MODEL in message  # which model
    assert str(tmp_path) in message  # which cache dir is at fault
    assert "indexed init" in message  # the remedy
    assert "--model" in message  # the remedy names the model


def test_is_model_cached_requires_weights(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Cached means the snapshot holds weight files, not just any file."""
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    snap = _hub_snapshot(tmp_path, "deadbeef")

    assert local._is_model_cached(MODEL) is False  # empty snapshot dir
    (snap / "config.json").write_text("{}")
    assert local._is_model_cached(MODEL) is False  # config-only residue
    (snap / "model.safetensors").write_bytes(b"\x00" * 8)
    assert local._is_model_cached(MODEL) is True  # weights landed
    (snap / "model.safetensors").unlink()
    (snap / "model.safetensors").symlink_to("../../blobs/never-completed")
    assert local._is_model_cached(MODEL) is False  # dangling symlink

    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty"))
    assert local._is_model_cached(MODEL) is False


def test_is_model_cached_uses_active_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """refs/main names the active revision; a config-only active one is not cached."""
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    rev_a = _hub_snapshot(tmp_path, "rev-a")
    rev_b = _hub_snapshot(tmp_path, "rev-b")
    (rev_a / "model.safetensors").write_bytes(b"\x00" * 8)
    (rev_b / "config.json").write_text("{}")
    refs_dir = rev_a.parent.parent / "refs"
    refs_dir.mkdir(parents=True)
    (refs_dir / "main").write_text("rev-b\n")

    assert local._is_model_cached(MODEL) is False  # active rev-b config-only
    (refs_dir / "main").write_text("rev-a")
    assert local._is_model_cached(MODEL) is True  # active rev-a has weights
    (refs_dir / "main").unlink()
    assert local._is_model_cached(MODEL) is True  # no ref → any weighted snap


# --------------------------------------------------------------------------
# Real-model tests (gated on the cached embedding model)
# --------------------------------------------------------------------------

requires_model = pytest.mark.skipif(
    not model_available(), reason="embedding model not cached"
)


@requires_model
def test_real_embedding_is_384_and_unit_normalized() -> None:
    embed = local.build_embed_model(CoreV2EmbeddingConfig())
    vec = embed.get_text_embedding("semantic search over local files")
    assert len(vec) == 384
    assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, abs_tol=1e-3)


@requires_model
def test_probe_dimension_returns_384() -> None:
    embed = local.build_embed_model(CoreV2EmbeddingConfig())
    assert local.probe_dimension(embed) == 384


@requires_model
def test_no_network_when_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cached model loads + embeds with zero outbound connections (R8/R12)."""

    class _NetworkAttempt(Exception):
        pass

    def blocked_connect(self, address):  # type: ignore[no-untyped-def]
        raise _NetworkAttempt(f"network connect attempted: {address}")

    def blocked_getaddrinfo(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise _NetworkAttempt(f"dns lookup attempted: {args}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(socket, "getaddrinfo", blocked_getaddrinfo)

    embed = local.build_embed_model(CoreV2EmbeddingConfig())
    vec = embed.get_text_embedding("offline probe")
    assert len(vec) == 384


@requires_model
def test_parity_with_v1_embedder_is_cosine_one() -> None:
    """v2 vectors match v1's SentenceEmbedder direction exactly (cosine ~= 1)."""
    embed = local.build_embed_model(CoreV2EmbeddingConfig())
    text = "The penguin migration survey recorded record numbers this austral summer."
    v2 = embed.get_text_embedding(text)

    # v1 embedder imported IN THE TEST only — tests are exempt from the
    # core.v2 -> core.v1 import-graph rule; source is not.
    from indexed.core.v1.engine.indexes.embeddings.sentence_embeder import (
        SentenceEmbedder,
    )

    v1 = [float(x) for x in SentenceEmbedder(MODEL).embed(text)]

    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    assert dot / (n1 * n2) > 0.9999


# --- cache-resolution parity guard (core-v2/2c) ------------------------------


def test_v2_cache_check_agrees_with_v1_cache_check() -> None:
    """v2's ``_is_model_cached`` must agree with v1's ``is_model_cached`` for the
    default model, so a future v1 cache-resolution edit can't silently drift v2
    into an offline cache miss (belt-and-suspenders; pure path checks, no model
    needed). Tests MAY import v1; source may not.
    """
    from indexed.core.v1.engine.indexes.embeddings.model_manager import (
        is_model_cached,
    )

    for name in (MODEL, "all-MiniLM-L6-v2"):
        assert local._is_model_cached(name) == is_model_cached(name), name
