"""Query-time git facts: repo root, changed paths, and last-touching commit.

Read-only, stdlib-only companion to ``connectors/files/change_tracker.py`` (which
answers the ingest-time question "what must be re-indexed"): this answers the
search-time questions. Nothing is cached globally — a long-lived MCP server must
never serve stale git facts. Every subprocess is timeout-bounded and every failure
degrades to ``None``/empty, so a git problem never breaks a search.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_TIMEOUT = 5

# Inherited from a hook environment, these redirect git at the OUTER repo —
# the same reason change_tracker scrubs them before every call.
_STRIPPED_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_CEILING_DIRECTORIES",
)

_LOG_FORMAT = "%H%x00%h%x00%an%x00%ae%x00%cI%x00%s"


def _env() -> dict[str, str]:
    """Child env: scrubbed of leaked GIT_* pointers, never promptable, C locale."""
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    return env


def _run(repo: str, *args: str) -> str | None:
    """Run one git command in ``repo``; stdout on success, ``None`` on any failure."""
    try:
        result = subprocess.run(
            # quotePath=false keeps a non-ASCII path literal; LC_ALL=C would
            # otherwise have git C-quote it into an unmatchable string.
            ["git", "-C", repo, "-c", "core.quotePath=false", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=_TIMEOUT,
            env=_env(),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _run_code(repo: str, *args: str) -> int | None:
    """Run one git command for its EXIT CODE; ``None`` when git could not run.

    ``_run`` folds a non-zero exit into ``None``, which cannot distinguish
    "git says no" (``merge-base --is-ancestor`` exit 1) from "git is broken".
    Freshness needs that distinction to report ``unknown`` honestly.
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo, "-c", "core.quotePath=false", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=_TIMEOUT,
            env=_env(),
        )
    except Exception:
        return None
    return result.returncode


def head_commit(repo: str) -> str | None:
    """Full SHA of HEAD, or ``None`` for an unborn/absent HEAD (or a non-repo)."""
    out = _run(repo, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    return out.strip() if out and out.strip() else None


def commit_exists(repo: str, commit: str) -> bool:
    """True when ``commit`` resolves in this repository (guards shallow/pruned)."""
    return (
        _run(repo, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
        is not None
    )


def is_ancestor(repo: str, ancestor: str, descendant: str) -> bool | None:
    """True/False from ``merge-base --is-ancestor``; ``None`` when git can't answer."""
    code = _run_code(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    if code is None:
        return None
    return code == 0


def commit_count(repo: str, older: str, newer: str) -> int | None:
    """Commits in ``older..newer``, or ``None`` when git cannot count them."""
    out = _run(repo, "rev-list", "--count", f"{older}..{newer}")
    if out is None:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


def is_detached_head(repo: str) -> bool:
    """True when HEAD is detached (not on a branch); ``False`` when unknown."""
    code = _run_code(repo, "symbolic-ref", "--quiet", "HEAD")
    return code == 1


def is_shallow_repository(repo: str) -> bool:
    """True for a shallow clone — its truncated history can't prove ancestry."""
    out = _run(repo, "rev-parse", "--is-shallow-repository")
    return bool(out and out.strip() == "true")


def ignored_paths(repo: str) -> frozenset[str] | None:
    """Untracked paths hidden by ``.gitignore`` — invisible to ``git status``.

    A file that was indexed and only LATER ignored still sits in the index;
    without this list freshness could call such a collection fresh forever.
    ``None`` when git cannot list them.
    """
    out = _run(repo, "ls-files", "-z", "--others", "--ignored", "--exclude-standard")
    if out is None:
        return None
    return frozenset(path for path in out.split("\0") if path)


def repo_toplevel(path: str) -> str | None:
    """Absolute repo root containing ``path``, or ``None`` when it is not in one."""
    out = _run(path, "rev-parse", "--show-toplevel")
    if out is None:
        return None
    top = out.strip()
    return top or None


def is_git_repo(path: str) -> bool:
    """True when ``path`` sits inside a git working tree."""
    return repo_toplevel(path) is not None


def changed_paths(repo: str, ref: str) -> frozenset[str] | None:
    """Repo-relative paths changed since ``ref``, INCLUDING uncommitted work.

    Covers committed, staged, unstaged and untracked paths. ``None`` when git
    cannot answer (not a repo, unborn HEAD, invalid ref) so the caller decides
    what to do; an invalid ref specifically must never look like "nothing
    changed", hence the explicit ``--verify`` pre-check.
    """
    if _run(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
        return None
    paths: set[str] = set()
    # ``git diff <ref> --`` compares REF's tree with the WORKING TREE, so one
    # leg covers committed, staged and unstaged changes alike; untracked paths
    # are the only ones it cannot see. Two legs, not four (#279 review).
    for args in (
        ("diff", "--name-only", "-z", ref, "--"),
        ("ls-files", "-z", "--others", "--exclude-standard"),
    ):
        out = _run(repo, *args)
        if out is None:
            return None
        paths.update(path for path in out.split("\0") if path)
    return frozenset(paths)


def last_commit(repo: str, path: str) -> dict[str, str] | None:
    """The commit that last touched ``path`` (repo-relative), or ``None``.

    ``None`` for an untracked path, a non-repo, or a path with no history — the
    caller omits the field rather than inventing provenance.
    """
    out = _run(repo, "log", "-1", f"--format={_LOG_FORMAT}", "--", f":(literal){path}")
    if out is None or not out.strip():
        return None
    fields = [f.replace("\x00", "").strip() for f in out.strip().split("\x00", 5)]
    if len(fields) < 6:
        return None
    commit, short, author, email, committed_at, subject = fields
    return {
        "commit": commit,
        "short": short,
        "author": author,
        "email": email,
        "committedAt": committed_at,
        "subject": subject[:200],
    }


_ZERO_SHA = "0" * 40

# Keys ``resolve_range`` returns for an attributed span. The internal ``epoch``
# and ``uncommitted`` markers never leave this module's public shape.
_SPAN_FIELDS = ("commit", "short", "author", "email", "committedAt", "subject")


def _iso_time(epoch: str, tz: str) -> str:
    """Porcelain's ``<epoch> <±HHMM>`` as the same ISO-8601 form git prints."""
    try:
        offset_seconds = 0
        if len(tz) == 5 and tz[0] in "+-":
            offset_seconds = int(tz[1:3]) * 3600 + int(tz[3:5]) * 60
            if tz[0] == "-":
                offset_seconds = -offset_seconds
        stamp = datetime.fromtimestamp(
            int(epoch), tz=timezone(timedelta(seconds=offset_seconds))
        )
    except (TypeError, ValueError, OSError):
        return ""
    return stamp.isoformat(timespec="seconds")


def _parse_porcelain(out: str) -> List[Optional[Dict[str, Any]]]:
    """Parse ``git blame --line-porcelain`` into one record per final line.

    ``--line-porcelain`` repeats the full header block for every line, so the
    parse is a flat scan: a 40-hex header line sets the destination line, the
    key/value lines fill the record, the leading-tab content line commits it.
    A line the output never covered stays ``None`` (never guessed).
    """
    records: Dict[int, Dict[str, Any]] = {}
    header: Dict[str, str] = {}
    final_line: Optional[int] = None
    for raw in out.splitlines():
        if raw.startswith("\t"):
            if final_line is not None:
                commit = header.get("commit", "")
                records[final_line] = {
                    "commit": commit,
                    "short": commit[:7],
                    "author": "" if commit == _ZERO_SHA else header.get("author", ""),
                    "email": "" if commit == _ZERO_SHA else header.get("email", ""),
                    "committedAt": ""
                    if commit == _ZERO_SHA
                    else _iso_time(
                        header.get("committer_epoch", ""),
                        header.get("committer_tz", ""),
                    ),
                    "subject": ""
                    if commit == _ZERO_SHA
                    else header.get("summary", "")[:200],
                    "epoch": 0
                    if commit == _ZERO_SHA
                    else int(header.get("epoch", "0") or 0),
                    "uncommitted": commit == _ZERO_SHA,
                }
            header = {}
            final_line = None
            continue
        if not raw:
            continue
        parts = raw.split(" ")
        if final_line is None and len(parts) >= 3 and len(parts[0]) == 40:
            header = {"commit": parts[0]}
            try:
                final_line = int(parts[2])
            except ValueError:
                final_line = None
            continue
        key, _, value = raw.partition(" ")
        if key == "author":
            header["author"] = value
        elif key == "author-mail":
            header["email"] = value.strip().lstrip("<").rstrip(">")
        elif key == "author-time":
            header["epoch"] = value
        elif key == "author-tz":
            header["tz"] = value
        elif key == "committer-time":
            header["committer_epoch"] = value
        elif key == "committer-tz":
            header["committer_tz"] = value
        elif key == "summary":
            header["summary"] = value
    if not records:
        return []
    return [records.get(line) for line in range(1, max(records) + 1)]


def _looks_binary(repo: str, path: str) -> bool:
    """Mirror git's own binary heuristic (a NUL in the first 8000 bytes).

    ``git blame`` happily returns the whole file as ONE line for a binary blob,
    which would let a caller attribute a "line span" that means nothing. The
    sniff is bounded and read-only; an unreadable path is not treated as binary
    (git will fail on it anyway).
    """
    try:
        with open(os.path.join(repo, path), "rb") as handle:
            return b"\x00" in handle.read(8000)
    except OSError:
        return False


def blame_lines(repo: str, path: str) -> Optional[List[Optional[Dict[str, Any]]]]:
    """One ``git blame --line-porcelain`` for ``path``, indexed by line (0-based).

    Returns ``None`` when git cannot answer at all — untracked path, non-repo,
    binary file, no history — so the caller omits the field instead of inventing
    provenance. One call per path, never per chunk: callers memoize by
    ``(repo, path)`` within a search.
    """
    if _looks_binary(repo, path):
        return None
    out = _run(repo, "blame", "--line-porcelain", "--", path)
    if out is None:
        return None
    return _parse_porcelain(out)


def resolve_range(
    lines: Optional[List[Optional[Dict[str, Any]]]],
    start_line: int,
    end_line: int,
) -> Optional[Dict[str, Any]]:
    """Attribute a 0-based, inclusive line span to its newest touching commit.

    The newest commit among the span's lines is the one that last touched it;
    ties resolve to the later line, so the answer is deterministic. Any
    uncommitted line in the span wins — a working-tree edit is the last touch,
    and reporting a committed ancestor as line-level provenance would be a
    whole-file guess wearing a line-level label. The span is reported back
    (1-based, as git counts lines) so a consumer can show what it covers.
    ``None`` when blame has no record for part of the span (unanswerable).
    """
    if lines is None or start_line < 0 or end_line < start_line:
        return None
    span = lines[start_line : end_line + 1]
    if len(span) != end_line - start_line + 1 or any(item is None for item in span):
        return None
    records = [item for item in span if item is not None]
    if any(record.get("uncommitted") for record in records):
        return {
            "uncommitted": True,
            "startLine": start_line + 1,
            "endLine": end_line + 1,
        }
    best = max(
        enumerate(records), key=lambda pair: (int(pair[1].get("epoch", 0)), pair[0])
    )[1]
    resolved = {key: best.get(key, "") for key in _SPAN_FIELDS}
    resolved["startLine"] = start_line + 1
    resolved["endLine"] = end_line + 1
    return resolved


def newest_touch(
    lines: Optional[List[Optional[Dict[str, Any]]]],
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """The newest blame record covering a chunk, for query-time SCORING (#144).

    The scoring counterpart of ``resolve_range``: it keeps the commit ``epoch``
    (the recency input), flags a working-tree touch instead of naming a commit,
    and falls back to the WHOLE file when the chunk recorded no usable line span
    — a span-less chunk still belongs to a document, and that document's newest
    line is the best recency evidence there is. Never used for the provenance
    contract: ``resolve_range`` stays the only source of ``chunk["git"]``.

    Returns ``{"epoch": int | None, "author", "email", "uncommitted"}``, or
    ``None`` when blame cannot answer at all.
    """
    if lines is None:
        return None
    records: List[Dict[str, Any]] = []
    if start_line is not None and end_line is not None:
        if 0 <= start_line <= end_line:
            span = lines[start_line : end_line + 1]
            if len(span) == end_line - start_line + 1:
                records = [item for item in span if item is not None]
    if not records:
        records = [item for item in lines if item is not None]
    if not records:
        return None
    if any(record.get("uncommitted") for record in records):
        # A working-tree line is the freshest possible touch; it has no epoch.
        return {"epoch": None, "author": "", "email": "", "uncommitted": True}
    best = max(
        enumerate(records), key=lambda pair: (int(pair[1].get("epoch", 0)), pair[0])
    )[1]
    return {
        "epoch": int(best.get("epoch", 0) or 0),
        "author": str(best.get("author", "")),
        "email": str(best.get("email", "")),
        "uncommitted": False,
    }


def recent_commit_count(repo: str, path: str, since_epoch: int) -> Optional[int]:
    """Commits touching ``path`` since ``since_epoch`` — the churn signal (#144).

    One ``git rev-list --count`` over the file's history inside the window
    (commit dates, as git defines ``--since``), repo-relative path, bounded like
    every other call here. The bound is formatted as ISO-8601 rather than passed
    as a bare epoch: git's date parser mishandles unix seconds past 2038.
    ``None`` when git cannot answer (unborn HEAD, not a repo), so a caller drops
    the signal rather than scoring a fabricated zero; an UNTRACKED path
    legitimately answers 0.
    """
    try:
        since = datetime.fromtimestamp(int(since_epoch), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    out = _run(
        repo,
        "rev-list",
        "--count",
        f"--since={since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "HEAD",
        "--",
        f":(literal){path}",
    )
    if out is None or not out.strip():
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


# Human-readable text for the ``reason`` codes a skipped ``changed_since`` carries
# (see ``core/v2/retrieval.py``). One table, shared by the MCP formatter and the
# CLI renderers, so "why was nothing filtered" reads the same on every surface.
_FILTER_SKIP_REASONS = {
    "no-git-repository": "no git repository could be resolved for the collection",
    "unknown-ref": "the git ref could not be resolved",
    "not-a-files-collection": "the collection has no files reader",
    "v1-engine": "git filtering applies to v2 collections only",
}


def filter_skip_message(status: dict) -> str:
    """One line explaining a ``gitFilter`` status that was not applied.

    ``status`` is the per-collection ``gitFilter`` dict; an unrecognized reason
    code is passed through verbatim rather than hidden.
    """
    reason = str(status.get("reason") or "unknown reason")
    return (
        f"changed_since '{status.get('ref', '')}' was not applied: "
        f"{_FILTER_SKIP_REASONS.get(reason, reason)}; results are unfiltered"
    )


# Why a requested git re-rank was not applied (#144). Same visible-degrade rule
# as the filter table above: a skipped option is named, never silently ignored.
_RERANK_SKIP_REASONS = {
    "no-git-repository": "no git repository could be resolved for the collection",
    "not-a-files-collection": "the collection has no files reader",
    "v1-engine": "git re-ranking applies to v2 collections only",
}


def rerank_skip_message(status: dict) -> str:
    """One line explaining a ``gitRerank`` status that was not applied."""
    reason = str(status.get("reason") or "unknown reason")
    return (
        "git re-ranking was not applied: "
        f"{_RERANK_SKIP_REASONS.get(reason, reason)}; "
        "results are ordered by similarity only"
    )


# Why a requested git annotation was not applied (dogfood M7). Same visible
# degrade rule: a document without attribution says why it has none.
_PROVENANCE_SKIP_REASONS = {
    "v1-engine": "git provenance applies to v2 collections only",
}


def provenance_skip_message(status: dict) -> str:
    """One line explaining a ``gitProvenance`` status that was not applied."""
    reason = str(status.get("reason") or "unknown reason")
    return (
        "git provenance was not applied: "
        f"{_PROVENANCE_SKIP_REASONS.get(reason, reason)}; "
        "results carry no commit attribution"
    )


_LINE_BLAME_SKIP_REASONS = {
    "v1-engine": "git line blame applies to v2 collections only",
}


def line_blame_skip_message(status: dict) -> str:
    """One line explaining a ``gitLineBlame`` status that was not applied."""
    reason = str(status.get("reason") or "unknown reason")
    return (
        "git line blame was not applied: "
        f"{_LINE_BLAME_SKIP_REASONS.get(reason, reason)}; "
        "hits carry no per-line attribution"
    )


def repo_relative(repo: str, base_path: str, source_id: str) -> str:
    """Repo-relative POSIX path for a document id.

    ``source_id`` is base-path-relative (see ``connectors/files/v1_adapter.py:35-36``),
    so it is joined onto ``base_path`` and normalised against ``repo`` — pure
    ``os.path`` arithmetic, never a filesystem probe (ids must not touch disk).
    """
    absolute = os.path.normpath(os.path.join(base_path, source_id))
    return os.path.relpath(absolute, repo).replace(os.sep, "/")


_MTIME_TOLERANCE = 1e-3


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string, or ``None`` when it is absent/unparseable."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def snapshot_is_current(
    base_path: str,
    source_id: str,
    modified_time: str | None,
    indexed_at: str | None = None,
) -> bool:
    """True when the file on disk still matches the mtime its indexed node holds.

    ``modified_time`` is written **offset-aware in UTC** by the files reader, so
    parsing it and taking ``.timestamp()`` is absolute — independent of the query
    process's zone or a DST change. An offset-less value is LEGACY (the old
    writers stored naive *local* wall time, whose zone is unknowable — the #279
    B1 defect): it is judged zone-free against ``indexed_at``, the manifest's UTC
    ``updatedTime``, because a file not newer than the index cannot have changed
    since. That degrades towards *provenance present*, as does a node with no
    timestamp at all. A vanished file always answers False, and the aware mtime
    equality is a heuristic, not a content hash.
    """
    path = os.path.normpath(os.path.join(base_path, source_id))
    try:
        actual = os.path.getmtime(path)
    except OSError:
        return False

    recorded = _parse_iso(modified_time)
    if recorded is not None and recorded.tzinfo is not None:
        # ``isoformat()`` keeps microseconds; anything beyond that rounding is an edit.
        return abs(recorded.timestamp() - actual) < _MTIME_TOLERANCE

    indexed = _parse_iso(indexed_at)
    if indexed is None or indexed.tzinfo is None:
        return True
    return actual <= indexed.timestamp() + _MTIME_TOLERANCE


__all__ = [
    "blame_lines",
    "changed_paths",
    "commit_count",
    "commit_exists",
    "filter_skip_message",
    "head_commit",
    "is_ancestor",
    "is_detached_head",
    "is_git_repo",
    "is_shallow_repository",
    "last_commit",
    "newest_touch",
    "recent_commit_count",
    "repo_relative",
    "repo_toplevel",
    "snapshot_is_current",
    "rerank_skip_message",
    "resolve_range",
]
