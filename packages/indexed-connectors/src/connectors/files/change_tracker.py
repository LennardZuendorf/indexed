"""Git-based and content-hash change tracking for incremental indexing."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from loguru import logger


@dataclass
class FileChange:
    """A single detected file change."""

    path: str
    status: Literal["added", "modified", "deleted"]


@dataclass
class IndexState:
    """Persisted state used to detect changes between indexing runs."""

    last_indexed_commit: str | None = None
    file_hashes: dict[str, str] | None = None
    last_indexed_at: str | None = None
    indexed_file_count: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, data: str) -> IndexState:
        return cls(**json.loads(data))


ChangeStrategy = Literal["auto", "git", "content_hash", "mtime", "none"]


class ChangeTracker:
    """Detect file-level changes using git, content hashing, or mtime."""

    def __init__(self, base_path: str, strategy: ChangeStrategy = "auto") -> None:
        self._base_path = base_path
        self._strategy = strategy

    def detect_changes(
        self, file_paths: list[str], state: IndexState
    ) -> list[FileChange]:
        """Return the list of file changes since the last indexing run."""
        effective = self._resolve_strategy()

        if effective == "none":
            return [
                FileChange(path=os.path.relpath(p, self._base_path), status="added")
                for p in file_paths
            ]

        if effective == "git":
            return self._git_changes(file_paths, state)

        if effective == "mtime":
            return self._mtime_changes(file_paths, state)

        # content_hash (default for non-git repos)
        return self._hash_changes(file_paths, state)

    def build_state(self, file_paths: list[str]) -> IndexState:
        """Build a fresh ``IndexState`` snapshot from the current files."""
        import datetime

        import xxhash

        hashes: dict[str, str] = {}
        for fp in file_paths:
            rel = os.path.relpath(fp, self._base_path)
            try:
                data = Path(fp).read_bytes()
                hashes[rel] = xxhash.xxh64(data).hexdigest()
            except OSError:
                pass

        commit = self._current_git_commit()

        return IndexState(
            last_indexed_commit=commit,
            file_hashes=hashes,
            last_indexed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            indexed_file_count=len(file_paths),
        )

    # -- strategy resolution ----------------------------------------------

    def _resolve_strategy(self) -> str:
        if self._strategy != "auto":
            return self._strategy
        if self._is_git_repo():
            return "git"
        return "content_hash"

    def _is_git_repo(self) -> bool:
        return (
            Path(self._base_path) / ".git"
        ).is_dir() or self._git_toplevel() is not None

    def _git_toplevel(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                cwd=self._base_path,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _current_git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self._base_path,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    # -- git strategy -----------------------------------------------------

    def _git_changes(
        self, file_paths: list[str], state: IndexState
    ) -> list[FileChange]:
        last_commit = state.last_indexed_commit
        current_commit = self._current_git_commit()

        if not current_commit:
            logger.warning("No git HEAD found; treating all files as added")
            return [
                FileChange(path=os.path.relpath(p, self._base_path), status="added")
                for p in file_paths
            ]

        if not last_commit:
            return [
                FileChange(path=os.path.relpath(p, self._base_path), status="added")
                for p in file_paths
            ]

        if last_commit == current_commit:
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", last_commit, current_commit],
                capture_output=True,
                text=True,
                cwd=self._base_path,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("git diff failed; treating all files as added")
                return [
                    FileChange(path=os.path.relpath(p, self._base_path), status="added")
                    for p in file_paths
                ]

            changes: list[FileChange] = []
            current_rel = {os.path.relpath(p, self._base_path) for p in file_paths}

            for line in result.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status_code = parts[0][0]  # A, M, D, R, C, etc.

                if status_code == "D":
                    rel = parts[1]
                    changes.append(FileChange(path=rel, status="deleted"))
                elif status_code == "A":
                    rel = parts[1]
                    if rel in current_rel:
                        changes.append(FileChange(path=rel, status="added"))
                elif status_code == "M":
                    rel = parts[1]
                    if rel in current_rel:
                        changes.append(FileChange(path=rel, status="modified"))
                elif status_code == "R":
                    old_rel = parts[1]
                    new_rel = parts[2] if len(parts) > 2 else parts[1]
                    changes.append(FileChange(path=old_rel, status="deleted"))
                    if new_rel in current_rel:
                        changes.append(FileChange(path=new_rel, status="added"))

            return changes

        except Exception:
            logger.opt(exception=True).warning(
                "git diff failed; treating all files as added"
            )
            return [
                FileChange(path=os.path.relpath(p, self._base_path), status="added")
                for p in file_paths
            ]

    # -- content-hash strategy --------------------------------------------

    def _hash_changes(
        self, file_paths: list[str], state: IndexState
    ) -> list[FileChange]:
        import xxhash

        old_hashes = state.file_hashes or {}
        changes: list[FileChange] = []
        seen: set[str] = set()

        for fp in file_paths:
            rel = os.path.relpath(fp, self._base_path)
            seen.add(rel)

            try:
                data = Path(fp).read_bytes()
                new_hash = xxhash.xxh64(data).hexdigest()
            except OSError:
                continue

            old_hash = old_hashes.get(rel)
            if old_hash is None:
                changes.append(FileChange(path=rel, status="added"))
            elif old_hash != new_hash:
                changes.append(FileChange(path=rel, status="modified"))

        # Detect deletions
        for rel in old_hashes:
            if rel not in seen:
                changes.append(FileChange(path=rel, status="deleted"))

        return changes

    # -- mtime strategy ---------------------------------------------------

    def _mtime_changes(
        self,
        file_paths: list[str],
        state: IndexState,
    ) -> list[FileChange]:
        old_hashes = state.file_hashes or {}
        changes: list[FileChange] = []
        seen: set[str] = set()

        last_indexed = state.last_indexed_at
        import datetime

        cutoff: float | None = None
        if last_indexed:
            try:
                cutoff = datetime.datetime.fromisoformat(last_indexed).timestamp()
            except ValueError:
                cutoff = None

        for fp in file_paths:
            rel = os.path.relpath(fp, self._base_path)
            seen.add(rel)

            if rel not in old_hashes:
                changes.append(FileChange(path=rel, status="added"))
            elif cutoff is not None:
                try:
                    mtime = os.path.getmtime(fp)
                    if mtime > cutoff:
                        changes.append(FileChange(path=rel, status="modified"))
                except OSError:
                    pass

        for rel in old_hashes:
            if rel not in seen:
                changes.append(FileChange(path=rel, status="deleted"))

        return changes
