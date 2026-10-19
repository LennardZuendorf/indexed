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


def _snapshot_has_weights(snapshot: Path) -> bool:
    """True when ``snapshot`` holds a real weights file.

    ``Path.exists()`` follows symlinks, so a dangling weight link (hub has not
    completed the blob) counts as absent — never as a loadable snapshot.
    """
    return any((snapshot / w).exists() for w in _WEIGHT_FILES)


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
    If not cached or force=True, downloads via huggingface_hub.

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
    path = acquire_with_retry(
        lambda: snapshot_download(repo_id=repo_id),
        model_name=model_name,
        action="download",
        cache_dir=cache_dir,
        cache_state=lambda: describe_cache_state(model_name),
    )

    # A "successful" call that left no weights is an honest failure, never a
    # false cached success (the download can finish with an empty/partial
    # snapshot on a flaky connection).
    snapshot = Path(path) if path else None
    if snapshot is None or not _snapshot_has_weights(snapshot):
        raise ModelAcquisitionError(
            model_name,
            action="download",
            category="corrupt",
            cache_dir=cache_dir,
            cache_state=describe_cache_state(model_name),
            cause="download completed without model weights",
        )

    logger.info(f"Model cached at: {path}")
    return path


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
