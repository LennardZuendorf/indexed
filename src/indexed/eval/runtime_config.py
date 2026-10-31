"""Scoped application configuration for measured evaluation runs."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import hashlib
import importlib.metadata
import os
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from indexed.eval.runner import RunConfig


def source_fingerprint(root: Path) -> str:
    """Hash source and dependency inputs, excluding generated eval artifacts."""
    paths = [*root.glob("src/**/*.py"), root / "pyproject.toml", root / "uv.lock"]
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def source_environment() -> dict[str, Any]:
    """Capture the actual measured worktree and numerical package versions."""
    root = Path(__file__).resolve().parents[3]

    def git(*args: str) -> str | None:
        """Return Git output, or None when source metadata cannot be read."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    versions = {}
    for name in (
        "numpy",
        "torch",
        "transformers",
        "sentence-transformers",
        "llama-index-core",
    ):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unknown"
    status = git("status", "--porcelain", "--untracked-files=normal")
    return {
        "indexed_git_rev": os.environ.get("GIT_COMMIT")
        or git("rev-parse", "HEAD")
        or "",
        "indexed_worktree_dirty": bool(status) if status is not None else None,
        "indexed_source_sha256": source_fingerprint(root),
        "numerical_dependencies": versions,
    }


@contextmanager
def evaluation_config(config: RunConfig) -> Generator[dict[str, Any], None, None]:
    """Pin the registered runtime settings and yield their validated values."""
    from indexed.cli.composition import register_app_config
    from indexed.config import get_config

    service = get_config()
    register_app_config(service)
    version = config.engine
    overrides = {
        "sources": None,
        "mcp": None,
        f"core.v{'1' if version == '2' else '2'}": None,
        "core.engine": version,
        f"core.v{version}.embedding.model_name": config.embedding_model,
        f"core.v{version}.embedding.batch_size": config.embedding_batch_size,
        f"core.v{version}.search.max_docs": config.max_docs,
        f"core.v{version}.search.score_threshold": (
            None
            if version == "1" and config.score_threshold == 0
            else config.score_threshold
        ),
        "core.v2.rerank.enabled": config.rerank,
        "core.v2.rerank.model": config.reranker_model,
        "core.v2.rerank.top_n": config.reranker_top_n,
    }
    with service.temporary_overlay(overrides):
        provider = service.bind()
        embedding = provider.get_by_path(f"core.v{version}.embedding").model_dump()
        search = provider.get_by_path(f"core.v{version}.search").model_dump()
        rerank = provider.get_by_path("core.v2.rerank").model_dump()
        yield {
            **config.as_dict(),
            "embedding_model": embedding["model_name"],
            "embedding_batch_size": embedding["batch_size"],
            "score_threshold": search["score_threshold"],
            "reranker_model": rerank["model"] if config.rerank else None,
            "reranker_top_n": rerank["top_n"] if config.rerank else None,
        }
