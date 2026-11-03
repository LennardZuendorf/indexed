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

_LOG_FORMAT = "%H%x00%h%x00%an%x00%ae%x00%aI%x00%s"


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
            timeout=_TIMEOUT,
            env=_env(),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


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
    for args in (
        ("diff", "--name-only", ref, "--"),
        ("diff", "--name-only", "--"),
        ("diff", "--name-only", "--cached", "--"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        out = _run(repo, *args)
        if out is None:
            return None
        paths.update(line.strip() for line in out.splitlines() if line.strip())
    return frozenset(paths)


def last_commit(repo: str, path: str) -> dict[str, str] | None:
    """The commit that last touched ``path`` (repo-relative), or ``None``.

    ``None`` for an untracked path, a non-repo, or a path with no history — the
    caller omits the field rather than inventing provenance.
    """
    out = _run(repo, "log", "-1", f"--format={_LOG_FORMAT}", "--", path)
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


def repo_relative(repo: str, base_path: str, source_id: str) -> str:
    """Repo-relative POSIX path for a document id.

    ``source_id`` is base-path-relative (see ``connectors/files/v1_adapter.py:35-36``),
    so it is joined onto ``base_path`` and normalised against ``repo`` — pure
    ``os.path`` arithmetic, never a filesystem probe (ids must not touch disk).
    """
    absolute = os.path.normpath(os.path.join(base_path, source_id))
    return os.path.relpath(absolute, repo).replace(os.sep, "/")


__all__ = [
    "changed_paths",
    "is_git_repo",
    "last_commit",
    "repo_relative",
    "repo_toplevel",
]
