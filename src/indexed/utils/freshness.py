"""Index freshness: how far behind the working tree is a collection's index?

The read-only reporting half of issue #146 (slice 1 — no git hooks). The
baseline is the files connector's own ``state.json`` (``last_indexed_commit`` +
``file_hashes``, written by ``ChangeTracker.build_state`` after a successful
create/update), so this module never invents persisted state.

Every verdict is one of three words, and every "cannot tell" path carries a
reason code — the same contract the ``gitFilter`` status established (#279):
a degraded answer is visible, never a fabricated ``fresh``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from indexed.utils import git_meta

FRESH = "fresh"
STALE = "stale"
UNKNOWN = "unknown"

# Reason codes for a verdict that is NOT fresh (``source-changed``) or could not
# be reached at all (everything else). Shared by CLI and MCP message tables.
SOURCE_CHANGED = "source-changed"
NOT_FILES = "not-a-files-collection"
NO_BASE_PATH = "no-base-path"
NO_BASELINE = "no-baseline"
NO_REPO = "no-git-repository"
NO_HEAD = "no-head"
HISTORY_MISSING = "history-missing"
HISTORY_REWRITTEN = "history-rewritten"
GIT_UNAVAILABLE = "git-unavailable"

_REASON_TEXT = {
    NOT_FILES: "the collection has no files source to compare",
    NO_BASE_PATH: "the collection's source directory is not recorded in its manifest",
    NO_BASELINE: "no baseline recorded (indexed before change tracking)",
    NO_REPO: "the source directory is not a git work tree",
    NO_HEAD: "the repository has no commits yet",
    HISTORY_MISSING: "the indexed commit is missing from this repository's history "
    "(shallow clone or pruned history)",
    HISTORY_REWRITTEN: "the indexed commit is no longer an ancestor of HEAD "
    "(history was rewritten)",
    GIT_UNAVAILABLE: "git could not answer",
    SOURCE_CHANGED: "the source changed since it was indexed",
}

_FILES_READER_TYPES = frozenset({"localFiles", "files"})


@dataclass(frozen=True)
class Freshness:
    """One collection's honest answer to "is the index still current?".

    ``files_changed``/``commits_behind`` are populated only when git actually
    counted them; a count that could not be established stays ``None`` rather
    than becoming a plausible-looking zero.
    """

    status: str
    reason: Optional[str] = None
    baseline: Optional[str] = None
    head: Optional[str] = None
    files_changed: Optional[int] = None
    commits_behind: Optional[int] = None
    detached_head: bool = False

    def summary(self) -> str:
        """The one line every surface prints — same verdict, same words."""
        if self.status == FRESH:
            line = "fresh — the index matches the working tree"
            if self.detached_head and self.head:
                line += f" (detached HEAD at {self.head})"
            return line
        if self.status == STALE:
            count = self.files_changed or 0
            line = f"stale — {count} {'file' if count == 1 else 'files'} changed"
            if self.baseline:
                line += f" since commit {self.baseline}"
            else:
                line += " since the index was built"
            if self.commits_behind:
                commits = f"{self.commits_behind} commit"
                commits += "" if self.commits_behind == 1 else "s"
                line += f" ({commits} behind HEAD)"
            return line
        return f"unknown — {_REASON_TEXT.get(self.reason or '', self.reason or 'no reason given')}"

    def to_dict(self) -> Dict[str, object]:
        """Machine-readable form; carries ``summary`` so no caller re-words it."""
        return {
            "status": self.status,
            "reason": self.reason,
            "baseline": self.baseline,
            "head": self.head,
            "filesChanged": self.files_changed,
            "commitsBehind": self.commits_behind,
            "detachedHead": self.detached_head,
            "summary": self.summary(),
        }


def read_baseline(
    collection_dir: str | Path,
) -> tuple[Optional[str], Optional[Dict[str, str]]]:
    """``(last_indexed_commit, file_hashes)`` from the files connector baseline.

    A missing, unreadable or partial ``state.json`` yields ``(None, None)`` —
    the caller reports ``unknown/no-baseline`` instead of guessing. Who owns
    this file: ``connectors/files/change_tracker.py::ChangeTracker.build_state``,
    persisted by the connector's ``post_run`` (v1 and v2 alike).
    """
    try:
        raw = json.loads((Path(collection_dir) / "state.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(raw, dict):
        return None, None
    commit = raw.get("last_indexed_commit") or None
    hashes = raw.get("file_hashes")
    return commit, hashes if isinstance(hashes, dict) else None


def evaluate(
    *,
    reader_type: Optional[str],
    source_path: Optional[str],
    baseline_commit: Optional[str],
    indexed_hashes: Optional[Dict[str, str]] = None,
) -> Freshness:
    """Compare the recorded baseline against the current working tree.

    Never raises: every git problem degrades to ``unknown`` with a reason.
    """
    if reader_type not in _FILES_READER_TYPES:
        return Freshness(UNKNOWN, reason=NOT_FILES)
    if not source_path or not os.path.isdir(source_path):
        return Freshness(UNKNOWN, reason=NO_BASE_PATH)

    repo = git_meta.repo_toplevel(source_path)
    if repo is None:
        return Freshness(UNKNOWN, reason=NO_REPO)
    head = git_meta.head_commit(repo)
    if head is None:
        return Freshness(UNKNOWN, reason=NO_HEAD)
    detached = git_meta.is_detached_head(repo)
    short_head = head[:7]
    if not baseline_commit:
        return Freshness(UNKNOWN, reason=NO_BASELINE, head=short_head)

    short_baseline = baseline_commit[:7]

    if baseline_commit == head:
        changed = git_meta.changed_paths(repo, head)
        if changed is None:
            return _unknown(GIT_UNAVAILABLE, short_baseline, short_head, detached)
        pending = _pending(
            repo=repo,
            source_path=source_path,
            repo_paths=_with_ignored(repo, source_path, changed, indexed_hashes),
            indexed_hashes=indexed_hashes,
        )
        return _verdict(
            pending,
            commits_behind=0,
            baseline=short_baseline,
            head=short_head,
            detached=detached,
        )

    # HEAD moved since the index was built: only a commit still IN this
    # history can be diffed honestly. A pruned commit means "cannot tell".
    if not git_meta.commit_exists(repo, baseline_commit):
        return _unknown(HISTORY_MISSING, short_baseline, short_head, detached)
    ancestor = git_meta.is_ancestor(repo, baseline_commit, head)
    if ancestor is None:
        return _unknown(GIT_UNAVAILABLE, short_baseline, short_head, detached)
    if ancestor is False:
        reason = (
            HISTORY_MISSING
            if git_meta.is_shallow_repository(repo)
            else HISTORY_REWRITTEN
        )
        return _unknown(reason, short_baseline, short_head, detached)

    changed = git_meta.changed_paths(repo, baseline_commit)
    if changed is None:
        return _unknown(GIT_UNAVAILABLE, short_baseline, short_head, detached)
    pending = _pending(
        repo=repo,
        source_path=source_path,
        repo_paths=_with_ignored(repo, source_path, changed, indexed_hashes),
        indexed_hashes=indexed_hashes,
    )
    return _verdict(
        pending,
        commits_behind=git_meta.commit_count(repo, baseline_commit, head),
        baseline=short_baseline,
        head=short_head,
        detached=detached,
    )


def _verdict(
    pending: set[str],
    *,
    commits_behind: Optional[int],
    baseline: str,
    head: str,
    detached: bool,
) -> Freshness:
    if not pending:
        return Freshness(
            FRESH,
            baseline=baseline,
            head=head,
            commits_behind=commits_behind,
            detached_head=detached,
        )
    return Freshness(
        STALE,
        reason=SOURCE_CHANGED,
        baseline=baseline,
        head=head,
        files_changed=len(pending),
        commits_behind=commits_behind,
        detached_head=detached,
    )


def _unknown(
    reason: str, baseline: Optional[str], head: str, detached: bool
) -> Freshness:
    return Freshness(
        UNKNOWN,
        reason=reason,
        baseline=baseline,
        head=head,
        detached_head=detached,
    )


def _with_ignored(
    repo: str,
    source_path: str,
    changed: set[str] | frozenset[str],
    indexed_hashes: Optional[Dict[str, str]],
) -> set[str]:
    """``changed`` plus files the index holds that are now ``.gitignore``-hidden.

    ``git status`` never reports those, so a file that was indexed and only
    later ignored would otherwise read ``fresh`` forever. Only paths already in
    the baseline are added — anything else was never indexed and is irrelevant.
    """
    candidates = set(changed)
    if not indexed_hashes:
        return candidates
    ignored = git_meta.ignored_paths(repo)
    if not ignored:
        return candidates
    rel_base = os.path.relpath(source_path, repo).replace(os.sep, "/")
    prefix = "" if rel_base == "." else f"{rel_base}/"
    candidates.update(
        path
        for path in ignored
        if path.startswith(prefix) and path[len(prefix) :] in indexed_hashes
    )
    return candidates


def _pending(
    *,
    repo: str,
    source_path: str,
    repo_paths: set[str] | frozenset[str],
    indexed_hashes: Optional[Dict[str, str]],
) -> set[str]:
    """Changed paths inside ``source_path`` that differ from the INDEXED bytes.

    Git can only say "differs from HEAD"; the index may legitimately hold
    uncommitted content (indexing a dirty tree is normal). Comparing the
    current bytes against the baseline hashes keeps that case ``fresh`` instead
    of reporting a change the index already contains. Without hashes we stay
    conservative and treat every changed path as pending.
    """
    rel_base = os.path.relpath(source_path, repo).replace(os.sep, "/")
    prefix = "" if rel_base == "." else f"{rel_base}/"
    inside: set[str] = set()
    for path in repo_paths:
        if prefix and not path.startswith(prefix):
            continue
        rel = path[len(prefix) :]
        if rel:
            inside.add(rel)
    if indexed_hashes is None:
        return inside

    import xxhash  # function-local: inspect/status must stay import-cheap

    pending: set[str] = set()
    for rel in inside:
        recorded = indexed_hashes.get(rel)
        if recorded is None:
            pending.add(rel)  # never indexed, or tracked under another key
            continue
        try:
            data = (Path(source_path) / rel).read_bytes()
        except OSError:
            pending.add(rel)  # deleted/unreadable: the index holds bytes the tree lacks
            continue
        if xxhash.xxh64(data).hexdigest() != recorded:
            pending.add(rel)
    return pending


__all__ = [
    "FRESH",
    "STALE",
    "UNKNOWN",
    "Freshness",
    "evaluate",
    "read_baseline",
]
