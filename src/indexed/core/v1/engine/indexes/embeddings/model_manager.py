"""Smart model cache manager for Indexed.

Works WITH the HuggingFace Hub cache instead of creating a separate one.
The HF cache (~/.cache/huggingface/hub/) is the single source of truth
for downloaded models. This module provides:

1. Detection: Is a model already cached (in HF cache)?
2. Download: Ensure a model is cached (idempotent).
3. Loading: Load with lru_cache, prefer local, warn if download needed.
4. Info: Report cache status for CLI display.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from indexed.core.errors import ModelAcquisitionError
from indexed.core.model_acquisition import (
    acquire_with_retry,
    local_load_error,
)
from indexed.utils.logger import enforce_third_party_policy

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "all-MiniLM-L6-v2"
SUPPORTED_MODELS = [
    "all-MiniLM-L6-v2",
    "all-MiniLM-L12-v2",
    "all-mpnet-base-v2",
    "paraphrase-MiniLM-L6-v2",
]

_ST_ORG = "sentence-transformers"

# A snapshot counts as cached only when a weight file is present: hub
# symlinks a snapshot file once its blob completes, so an interrupted
# download leaves config/tokenizer files without weights.
_WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")

# Files a transformers tokenizer class loads from. A repo ships the one its
# tokenizer type needs, so every variant is allow-listed: a list that knows
# only `tokenizer.json` would leave a sentencepiece-only repo unloadable while
# still counting as cached.
_TOKENIZER_FILES = (
    "merges.txt",
    "sentencepiece.bpe.model",
    "spiece.model",
    "spm.model",
    "tokenizer.json",
    "tokenizer.model",
    "vocab.json",
    "vocab.txt",
)

# The files the embedder actually loads for the default backend: safetensors
# weights, the tokenizer, the sentence-transformers module payloads and the
# model/ST configs. Without an allow-list `snapshot_download` also fetches the
# ONNX, OpenVINO, TF, Rust and torch-`.bin` variants nobody loads — a 889 MB
# cache to get the 88 MB this list covers (a first `index create` downloads
# exactly these). The ONNX export is an optional acceleration that both
# engines survive without, so it is not pre-fetched: `load_model` attempts it
# from the cached snapshot and falls back to torch.
#
# Module directories are named per model (`1_Pooling`, `2_Dense`, ...), so the
# list matches their payload shapes rather than one model's layout: a Dense
# head missing from a multilingual model is a load failure, not a saved byte.
# Payloads that fit no shape here are fetched on demand from the repo's own
# `modules.json` (see `_missing_module_dirs`).
_MODEL_ALLOW_PATTERNS = [
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer_config.json",
    *_TOKENIZER_FILES,
    "*/config.json",
    "*/model.safetensors",
    "*/pytorch_model.bin",
]


def _snapshot_has_weights(snapshot: Path) -> bool:
    """True when ``snapshot`` holds a real weights file.

    ``Path.exists()`` follows symlinks, so a dangling weight link (hub has not
    completed the blob) counts as absent — never as a loadable snapshot.
    """
    return any((snapshot / w).exists() for w in _WEIGHT_FILES)


def _referenced_module_dirs(snapshot: Path) -> list[str]:
    """Module directories the repo's own ``modules.json`` names.

    ``modules.json`` is the registry sentence-transformers loads from, so it —
    not a list hardcoded here — says which directories the loader will open.
    The root Transformer module uses an empty path and is skipped.
    """
    modules_file = snapshot / "modules.json"
    if not modules_file.is_file():
        return []
    try:
        entries = json.loads(modules_file.read_text())
    except (OSError, ValueError):
        # An unreadable registry is a broken repository, not a filtered
        # download: a wider snapshot cannot fix it, so do not retry.
        return []
    if not isinstance(entries, list):
        return []

    paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str):
            path = path.strip().strip("/")
            if path and path != ".":
                paths.append(path)
    return paths


def _missing_module_dirs(snapshot: Path) -> list[str]:
    """Referenced module directories the filtered snapshot does not hold."""
    return [p for p in _referenced_module_dirs(snapshot) if not (snapshot / p).is_dir()]


def _tokenizer_missing(snapshot: Path) -> bool:
    """True when the repo declares a tokenizer but no artifact landed.

    ``tokenizer_config.json`` is the repo's own statement that it ships a
    tokenizer; ``_TOKENIZER_FILES`` covers every artifact the transformers
    tokenizer classes load from. This firing means the repo uses a layout the
    filter cannot name — the one case the full snapshot is still justified.
    """
    if not (snapshot / "tokenizer_config.json").exists():
        return False
    return not any((snapshot / f).exists() for f in _TOKENIZER_FILES)


def _get_hf_cache_dir() -> Path:
    """Resolve the active HuggingFace Hub cache directory.

    Priority: HF_HUB_CACHE > HF_HOME/hub > ~/.cache/huggingface/hub
    """
    if env := os.environ.get("HF_HUB_CACHE"):
        return Path(env)
    hf_home = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    return Path(hf_home) / "hub"


def _model_repo_id(model_name: str) -> str:
    """Convert a short model name to a full HF repo ID.

    'all-MiniLM-L6-v2' -> 'sentence-transformers/all-MiniLM-L6-v2'
    Already-qualified names like 'org/model' are returned as-is.
    """
    if "/" in model_name:
        return model_name
    return f"{_ST_ORG}/{model_name}"


def _hf_cache_model_dir(model_name: str) -> Path:
    """Return the expected HF cache directory for a model."""
    repo_id = _model_repo_id(model_name)
    folder_name = f"models--{repo_id.replace('/', '--')}"
    return _get_hf_cache_dir() / folder_name


def _select_cached_snapshot(model_name: str) -> Path | None:
    """The weights-bearing snapshot the cache predicate resolves, or ``None``.

    Single source of truth for both ``is_model_cached`` and
    ``_resolve_snapshot_path``, so "cached" and "the snapshot we load" can
    never disagree. Hub resolves the default revision via refs/main: only that
    snapshot decides, so a stale complete snapshot cannot mask the active one.
    With no refs/main, the first weights-bearing snapshot wins.
    """
    snapshots_dir = _hf_cache_model_dir(model_name) / "snapshots"
    if not snapshots_dir.is_dir():
        return None

    refs_main = _hf_cache_model_dir(model_name) / "refs" / "main"
    if refs_main.exists():
        active = snapshots_dir / refs_main.read_text().strip()
        return active if _snapshot_has_weights(active) else None

    for snapshot in sorted(snapshots_dir.iterdir()):
        if snapshot.is_dir() and _snapshot_has_weights(snapshot):
            return snapshot
    return None


def is_model_cached(model_name: str = DEFAULT_MODEL) -> bool:
    """True when a snapshot holds model weights (pure path checks).

    This does NOT import any heavy libraries. Weights must be present — an
    interrupted download leaves config files without weights, and a
    weights-blind "any file" check would pin the load offline to fail on
    the missing weights instead of re-downloading. Mirrored by core.v2's
    ``_is_model_cached``.
    """
    return _select_cached_snapshot(model_name) is not None


def describe_cache_state(model_name: str = DEFAULT_MODEL) -> str:
    """Human-readable cache state for diagnostics (pure path checks)."""
    if is_model_cached(model_name):
        return "cached, weights present"
    if not _hf_cache_model_dir(model_name).exists():
        return "not cached"
    return "incomplete, weights missing"


def ensure_model(model_name: str = DEFAULT_MODEL, force: bool = False) -> str:
    """Ensure a model is present in the HuggingFace cache.

    If already cached and force=False, returns immediately (no network call).
    If not cached or force=True, downloads via huggingface_hub — the
    embedder's own file set (``_MODEL_ALLOW_PATTERNS``), not the whole
    repository with every runtime variant — and then proves that set is
    complete before reporting success.

    Returns:
        The local path to the snapshot directory.
    """
    if not force and is_model_cached(model_name):
        logger.info(f"Model '{model_name}' found in HuggingFace cache.")
        return _resolve_snapshot_path(model_name)

    logger.info(f"Downloading model '{model_name}' to HuggingFace cache...")

    from huggingface_hub import snapshot_download

    # HF reconfigures its own logger at import (StreamHandler + WARNING) —
    # re-assert the policy or the Hub notice prints twice (#211).
    enforce_third_party_policy("huggingface_hub")

    repo_id = _model_repo_id(model_name)
    cache_dir = _get_hf_cache_dir()
    patterns = list(_MODEL_ALLOW_PATTERNS)

    def download(allow_patterns: list[str] | None) -> Path | None:
        def call() -> str:
            if allow_patterns is None:
                return snapshot_download(repo_id=repo_id)
            return snapshot_download(repo_id=repo_id, allow_patterns=allow_patterns)

        path = acquire_with_retry(
            call,
            model_name=model_name,
            action="download",
            cache_dir=cache_dir,
            cache_state=lambda: describe_cache_state(model_name),
        )
        return Path(path) if path else None

    snapshot = download(patterns)
    if snapshot is None or not _snapshot_has_weights(snapshot):
        # The allow-list is a bandwidth optimization, never a correctness
        # gate: a repo that publishes only a variant we do not pre-fetch
        # (a lone pytorch_model.bin, say) must still initialize, so fall back
        # to the full snapshot before declaring the download corrupt.
        logger.debug(
            f"Filtered snapshot of '{model_name}' has no weights; "
            f"retrying with the full repository snapshot."
        )
        snapshot = download(None) or snapshot
    else:
        missing = _missing_module_dirs(snapshot)
        if missing:
            # Module payloads are named per model, so the allow-list can miss
            # one. Ask the repo for everything under each module its own
            # modules.json names: a directory the repo fills lands here, while
            # one it leaves empty (a parameterless module such as 2_Normalize)
            # stays absent — that is the loader's normal case, not a gap, and
            # a full-snapshot download would not create it either.
            logger.debug(
                f"Filtered snapshot of '{model_name}' lacks module dirs "
                f"{missing}; fetching them from the repository."
            )
            snapshot = download(patterns + [f"{p}/*" for p in missing]) or snapshot

        if _tokenizer_missing(snapshot):
            # The repo declares a tokenizer but none of the artifacts the
            # transformers tokenizer classes read landed: only a layout the
            # filter cannot name does that, so one full snapshot is justified.
            logger.debug(
                f"Filtered snapshot of '{model_name}' has no tokenizer artifacts; "
                f"retrying with the full repository snapshot."
            )
            snapshot = download(None) or snapshot

    # A "successful" call that left no weights is an honest failure, never a
    # false cached success (the download can finish with an empty/partial
    # snapshot on a flaky connection).
    if snapshot is None or not _snapshot_has_weights(snapshot):
        raise ModelAcquisitionError(
            model_name,
            action="download",
            category="corrupt",
            cache_dir=cache_dir,
            cache_state=describe_cache_state(model_name),
            cause="download completed without model weights",
        )

    logger.info(f"Model cached at: {snapshot}")
    return str(snapshot)


def _resolve_snapshot_path(model_name: str) -> str:
    """Resolve the weights-bearing snapshot that ``is_model_cached`` validated.

    Delegates to ``_select_cached_snapshot`` so the loader's snapshot is
    exactly the one the predicate approved — the old fallback could return the
    first non-empty snapshot (config-only residue) and report a false cached
    success.
    """
    snapshot = _select_cached_snapshot(model_name)
    if snapshot is None:
        raise FileNotFoundError(
            f"Model '{model_name}' appears cached but no valid snapshot found. "
            f"Run 'indexed init --force' to re-download."
        )
    return str(snapshot)


def _has_onnx_model(model_name: str) -> bool:
    """Check if an ONNX-exported model exists in the HF cache."""
    model_dir = _hf_cache_model_dir(model_name)
    snapshots_dir = model_dir / "snapshots"
    if not snapshots_dir.exists():
        return False
    for snapshot in snapshots_dir.iterdir():
        if snapshot.is_dir():
            onnx_dir = snapshot / "onnx"
            if onnx_dir.exists() and any(onnx_dir.glob("*.onnx")):
                return True
            if any(snapshot.glob("*.onnx")):
                return True
    return False


@lru_cache(maxsize=4)
def load_model(model_name: str = DEFAULT_MODEL) -> SentenceTransformer:
    """Load an embedding model, leveraging the HuggingFace cache.

    Loading strategy:
    1. Try ONNX backend first (faster inference, no PyTorch import needed)
    2. If ONNX unavailable, fall back to default PyTorch backend
    3. If model is in HF cache -> load with local_files_only=True (no network)
    4. If not cached -> warn user, download, cache for next time

    The model is cached in memory (lru_cache) for the process lifetime.
    """
    from sentence_transformers import SentenceTransformer

    # SentenceTransformers pulls huggingface_hub in, which reconfigures its own
    # logger at import — re-assert the policy before it can log (#211).
    enforce_third_party_policy("huggingface_hub")

    repo_id = _model_repo_id(model_name)
    cached = is_model_cached(model_name)
    cache_dir = _get_hf_cache_dir()

    # Try ONNX backend for faster inference (avoids heavy PyTorch overhead)
    if cached:
        # Load the exact snapshot the cache predicate validated (not the repo
        # id) so "cached" and "loaded" can never diverge, and so an offline
        # load never depends on the Hub resolving refs/main again.
        snapshot = _resolve_snapshot_path(model_name)
        logger.debug(f"Loading '{model_name}' from HuggingFace cache (offline).")
        try:
            try:
                model = SentenceTransformer(
                    snapshot,
                    local_files_only=True,
                    backend="onnx",
                )
                logger.debug(f"Loaded '{model_name}' with ONNX backend.")
                return model
            except Exception as e:
                logger.debug(
                    f"ONNX backend unavailable for '{model_name}' ({e}), "
                    f"falling back to default backend."
                )
                return SentenceTransformer(snapshot, local_files_only=True)
        except Exception as exc:
            # Cache predicate said "cached" and the offline load still failed:
            # a corrupt/incomplete snapshot, never a network problem.
            raise local_load_error(
                exc,
                model_name=model_name,
                cache_dir=cache_dir,
                cache_state=describe_cache_state(model_name),
            ) from exc

    logger.warning(
        f"Model '{model_name}' not found in cache. "
        f"Downloading now (run 'indexed init' to pre-download models)."
    )

    def _download_and_load() -> SentenceTransformer:
        try:
            model = SentenceTransformer(repo_id, backend="onnx")
            logger.debug(f"Downloaded and loaded '{model_name}' with ONNX backend.")
            return model
        except Exception:
            return SentenceTransformer(repo_id)

    return acquire_with_retry(
        _download_and_load,
        model_name=model_name,
        action="download",
        cache_dir=cache_dir,
        cache_state=lambda: describe_cache_state(model_name),
    )


def get_cache_info() -> dict:
    """Return information about cached embedding models for display.

    Uses huggingface_hub.scan_cache_dir() for accurate size reporting,
    filtered to only sentence-transformers models.
    Falls back to manual directory inspection if scan_cache_dir fails.
    """
    cache_dir = _get_hf_cache_dir()

    try:
        from huggingface_hub import scan_cache_dir

        enforce_third_party_policy("huggingface_hub")

        cache_info = scan_cache_dir(cache_dir)
        models = []
        for repo in cache_info.repos:
            if repo.repo_type == "model" and (
                repo.repo_id.startswith(f"{_ST_ORG}/")
                or repo.repo_id in SUPPORTED_MODELS
            ):
                models.append(
                    {
                        "name": repo.repo_id,
                        "size_mb": round(repo.size_on_disk / (1024 * 1024), 1),
                        "revisions": len(repo.revisions),
                        "last_modified": repo.last_modified,
                        "path": str(repo.repo_path),
                    }
                )

        return {
            "cache_dir": str(cache_dir),
            "models": models,
            "total_size_mb": round(sum(float(m["size_mb"]) for m in models), 1),
        }

    except Exception as e:
        logger.debug(f"scan_cache_dir failed ({e}), falling back to manual scan")
        models = []
        for name in SUPPORTED_MODELS:
            if is_model_cached(name):
                model_dir = _hf_cache_model_dir(name)
                size = sum(
                    f.stat().st_size
                    for f in model_dir.rglob("*")
                    if f.is_file() and not f.is_symlink()
                ) / (1024 * 1024)
                models.append(
                    {
                        "name": f"{_ST_ORG}/{name}",
                        "size_mb": round(size, 1),
                        "path": str(model_dir),
                    }
                )
        return {
            "cache_dir": str(cache_dir),
            "models": models,
            "total_size_mb": round(sum(float(m["size_mb"]) for m in models), 1),
        }
