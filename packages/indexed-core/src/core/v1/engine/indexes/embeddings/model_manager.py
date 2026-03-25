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


def is_model_cached(model_name: str = DEFAULT_MODEL) -> bool:
    """Check if a model exists in the HuggingFace Hub cache.

    This does NOT import any heavy libraries — it's pure path checks.
    """
    model_dir = _hf_cache_model_dir(model_name)
    if not model_dir.exists():
        return False

    snapshots_dir = model_dir / "snapshots"
    if not snapshots_dir.exists():
        return False

    for snapshot in snapshots_dir.iterdir():
        if snapshot.is_dir() and any(snapshot.iterdir()):
            return True

    return False


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

    repo_id = _model_repo_id(model_name)
    path = snapshot_download(repo_id=repo_id)
    logger.info(f"Model cached at: {path}")
    return path


def _resolve_snapshot_path(model_name: str) -> str:
    """Resolve the path to the latest snapshot for a cached model."""
    model_dir = _hf_cache_model_dir(model_name)
    refs_main = model_dir / "refs" / "main"

    if refs_main.exists():
        commit_hash = refs_main.read_text().strip()
        snapshot_path = model_dir / "snapshots" / commit_hash
        if snapshot_path.exists():
            return str(snapshot_path)

    # Fallback: return the first snapshot directory found
    snapshots_dir = model_dir / "snapshots"
    for snapshot in sorted(snapshots_dir.iterdir()):
        if snapshot.is_dir() and any(snapshot.iterdir()):
            return str(snapshot)

    raise FileNotFoundError(
        f"Model '{model_name}' appears cached but no valid snapshot found. "
        f"Run 'indexed init --force' to re-download."
    )


@lru_cache(maxsize=4)
def load_model(model_name: str = DEFAULT_MODEL) -> SentenceTransformer:
    """Load an embedding model, leveraging the HuggingFace cache.

    Loading strategy:
    1. If model is in HF cache -> load with local_files_only=True (no network)
    2. If not cached -> warn user, download, cache for next time

    The model is cached in memory (lru_cache) for the process lifetime.
    """
    from sentence_transformers import SentenceTransformer

    repo_id = _model_repo_id(model_name)

    if is_model_cached(model_name):
        logger.debug(f"Loading '{model_name}' from HuggingFace cache (offline).")
        return SentenceTransformer(repo_id, local_files_only=True)

    logger.warning(
        f"Model '{model_name}' not found in cache. "
        f"Downloading now (run 'indexed init' to pre-download models)."
    )
    return SentenceTransformer(repo_id)


def get_cache_info() -> dict:
    """Return information about cached embedding models for display.

    Uses huggingface_hub.scan_cache_dir() for accurate size reporting,
    filtered to only sentence-transformers models.
    Falls back to manual directory inspection if scan_cache_dir fails.
    """
    cache_dir = _get_hf_cache_dir()

    try:
        from huggingface_hub import scan_cache_dir

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
            "total_size_mb": round(sum(m["size_mb"] for m in models), 1),
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
            "total_size_mb": round(sum(m["size_mb"] for m in models), 1),
        }
