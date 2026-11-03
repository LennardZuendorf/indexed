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
    out = _run(repo, "ls-files", "--others", "--ignored", "--exclude-standard")
    if out is None:
        return None
    return frozenset(line.strip() for line in out.splitlines() if line.strip())


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
    "commit_count",
    "commit_exists",
    "filter_skip_message",
    "head_commit",
    "is_ancestor",
    "is_detached_head",
    "is_git_repo",
    "is_shallow_repository",
    "last_commit",
    "repo_relative",
    "repo_toplevel",
]
