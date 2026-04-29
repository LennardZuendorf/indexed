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
        git_toplevel = self._git_toplevel()

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

        current_rel = {os.path.relpath(p, self._base_path) for p in file_paths}

        # Collect committed changes between last_commit and HEAD
        committed: dict[str, Literal["added", "modified", "deleted"]] = {}
        if last_commit != current_commit:
            try:
                result = subprocess.run(
                    ["git", "diff", "--name-status", last_commit, current_commit],
                    capture_output=True,
                    text=True,
                    cwd=self._base_path,
                    timeout=30,
                )
                if result.returncode == 0:
                    committed = self._parse_diff_name_status(
                        result.stdout, git_toplevel, current_rel
                    )
                else:
                    logger.warning("git diff failed; falling back to full re-index")
                    return [FileChange(path=p, status="added") for p in current_rel]
            except Exception:
                logger.opt(exception=True).warning(
                    "git diff failed; falling back to full re-index"
                )
                return [FileChange(path=p, status="added") for p in current_rel]

        # Collect uncommitted changes (staged + unstaged) via git status
        uncommitted: dict[str, Literal["added", "modified", "deleted"]] = {}
        try:
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self._base_path,
                timeout=30,
            )
            if status_result.returncode == 0:
                uncommitted = self._parse_status_porcelain(
                    status_result.stdout, git_toplevel, current_rel
                )
        except Exception:
            logger.opt(exception=True).warning(
                "git status failed; uncommitted changes may be missed"
            )

        # Merge: uncommitted takes precedence over committed for same paths
        merged: dict[str, Literal["added", "modified", "deleted"]] = {
            **committed,
            **uncommitted,
        }

        # Detect files that were indexed before but are no longer in the current
        # walk (e.g. newly added to .gitignore, matched a new exclude pattern, or
        # deleted outside of git). git diff/status won't surface these.
        if state.file_hashes:
            for rel in state.file_hashes:
                if rel not in current_rel and rel not in merged:
                    merged[rel] = "deleted"

        return [FileChange(path=p, status=s) for p, s in merged.items()]

    def _git_path_to_rel(self, git_path: str, git_toplevel: str | None) -> str | None:
        """Convert a repo-root-relative git path to a base_path-relative path.

        Returns None if the path is outside base_path.
        """
        if git_toplevel:
            abs_path = os.path.join(git_toplevel, git_path)
        else:
            abs_path = os.path.join(self._base_path, git_path)

        rel = os.path.relpath(abs_path, self._base_path)
        if rel.startswith(".."):
            return None  # outside base_path
        return rel

    def _parse_diff_name_status(
        self,
        output: str,
        git_toplevel: str | None,
        current_rel: set[str],
    ) -> dict[str, Literal["added", "modified", "deleted"]]:
        """Parse ``git diff --name-status`` output into a change dict."""
        result: dict[str, Literal["added", "modified", "deleted"]] = {}
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            code = parts[0][0]
            if code == "D":
                rel = self._git_path_to_rel(parts[1], git_toplevel)
                if rel is not None:
                    result[rel] = "deleted"
            elif code == "A":
                rel = self._git_path_to_rel(parts[1], git_toplevel)
                if rel is not None and rel in current_rel:
                    result[rel] = "added"
            elif code == "M":
                rel = self._git_path_to_rel(parts[1], git_toplevel)
                if rel is not None and rel in current_rel:
                    result[rel] = "modified"
            elif code == "R":
                old_rel = self._git_path_to_rel(parts[1], git_toplevel)
                new_rel = self._git_path_to_rel(
                    parts[2] if len(parts) > 2 else parts[1], git_toplevel
                )
                if old_rel is not None:
                    result[old_rel] = "deleted"
                if new_rel is not None and new_rel in current_rel:
                    result[new_rel] = "added"
        return result

    def _parse_status_porcelain(
        self,
        output: str,
        git_toplevel: str | None,
        current_rel: set[str],
    ) -> dict[str, Literal["added", "modified", "deleted"]]:
        """Parse ``git status --porcelain`` output into a change dict.

        Covers staged, unstaged, and untracked files.
        """
        result: dict[str, Literal["added", "modified", "deleted"]] = {}
        for line in output.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            git_path = line[3:].strip()

            # Handle renames: "old -> new" format
            if " -> " in git_path:
                old_part, new_part = git_path.split(" -> ", 1)
                old_rel = self._git_path_to_rel(old_part.strip(), git_toplevel)
                new_rel = self._git_path_to_rel(new_part.strip(), git_toplevel)
                if old_rel is not None:
                    result[old_rel] = "deleted"
                if new_rel is not None and new_rel in current_rel:
                    result[new_rel] = "added"
                continue

            rel = self._git_path_to_rel(git_path, git_toplevel)
            if rel is None:
                continue

            # XY codes: X = staged, Y = unstaged; '?' = untracked
            x, y = xy[0], xy[1]
            if x == "D" or y == "D":
                result[rel] = "deleted"
            elif x == "?" or (x == "A" and y in ("A", " ", "?")):
                if rel in current_rel:
                    result[rel] = "added"
            elif x in ("M", "A", "R", "C") or y == "M":
                if rel in current_rel:
                    result[rel] = "modified"

        return result

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
