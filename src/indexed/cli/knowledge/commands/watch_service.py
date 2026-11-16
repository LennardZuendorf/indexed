"""Polling file watcher for one collection — foreground only, no daemon.

The loop runs only while ``indexed index watch <collection>`` is running, so no
background process exists and the CLI cold start is untouched (no inotify
dependency, no module-level engine/ML import). Polling also survives network
filesystems, where inotify-style events are unreliable.

The scan is only a *wake-up signal*: the real delta detection is the connector's
change tracker inside ``update``, which skips unchanged documents by content
hash. A false-positive scan therefore costs one cheap pass — never a rebuild.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from indexed.connectors.files.schema import DEFAULT_EXCLUDED_DIRS

MAX_CONSECUTIVE_FAILURES = 3


@dataclass(frozen=True)
class WatchSignature:
    """Cheap fingerprint of the watched tree: file count + path/size/mtime digest."""

    files: int
    digest: str


def _load_gitignore(directory: Path) -> Any | None:
    """Return a compiled ``PathSpec`` for ``directory/.gitignore``, else ``None``.

    A malformed or unreadable .gitignore is treated as absent — the scan is a
    wake-up signal, so a missed exclusion only costs one extra pass.
    """
    gitignore = directory / ".gitignore"
    if not gitignore.is_file():
        return None
    try:
        import pathspec

        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except Exception:
        return None


def _relative(directory: Path, spec_dir: Path) -> str | None:
    try:
        return directory.relative_to(spec_dir).as_posix()
    except ValueError:
        return None


def _is_dir_ignored(directory: Path, specs: Sequence[tuple[Path, Any]]) -> bool:
    for spec_dir, spec in specs:
        rel = _relative(directory, spec_dir)
        if rel is not None and (spec.match_file(rel + "/") or spec.match_file(rel)):
            return True
    return False


def _is_file_ignored(path: Path, specs: Sequence[tuple[Path, Any]]) -> bool:
    for spec_dir, spec in specs:
        rel = _relative(path, spec_dir)
        if rel is not None and spec.match_file(rel):
            return True
    return False


def iter_watched_files(
    base_path: str | Path,
    *,
    excluded_dirs: Sequence[str] = (),
    respect_gitignore: bool = True,
    excluded_paths: Sequence[Path] = (),
) -> Iterator[Path]:
    """Yield the files a ``localFiles`` collection reads from ``base_path``.

    Mirrors the reader's directory pruning (excluded dir names + per-directory
    .gitignore), so editing an ignored file wakes no update. Include/negation
    patterns are deliberately NOT applied: a file the reader filters out can
    only cause one extra no-op pass, never a missed change.
    """
    base = Path(base_path)
    excluded = set(excluded_dirs or DEFAULT_EXCLUDED_DIRS)
    excluded_roots = {path.resolve() for path in excluded_paths}
    specs: list[tuple[Path, Any]] = []
    for root, dirs, files in os.walk(base, topdown=True):
        root_path = Path(root)
        if respect_gitignore:
            spec = _load_gitignore(root_path)
            if spec is not None:
                specs.append((root_path, spec))
        dirs[:] = [
            name
            for name in dirs
            if name not in excluded
            and (root_path / name).resolve() not in excluded_roots
            and not _is_dir_ignored(root_path / name, specs)
        ]
        for name in files:
            path = root_path / name
            if path.is_file() and not _is_file_ignored(path, specs):
                yield path


def signature_for(
    base_path: str | Path,
    *,
    excluded_dirs: Sequence[str] = (),
    respect_gitignore: bool = True,
    excluded_paths: Sequence[Path] = (),
) -> WatchSignature | None:
    """Fingerprint the watched tree, or ``None`` when ``base_path`` is not a dir.

    ``None`` is the documented failure signal: a missing source path must never
    reach ``update``, because an empty walk would classify every indexed file as
    deleted and empty the collection.
    """
    base = Path(base_path)
    if not base.is_dir():
        return None
    digest = hashlib.blake2b(digest_size=16)
    count = 0
    for path in sorted(
        iter_watched_files(
            base,
            excluded_dirs=excluded_dirs,
            respect_gitignore=respect_gitignore,
            excluded_paths=excluded_paths,
        )
    ):
        try:
            stat = path.stat()
        except OSError:
            continue
        count += 1
        relative = path.relative_to(base).as_posix()
        digest.update(f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
    return WatchSignature(files=count, digest=digest.hexdigest())


@dataclass(frozen=True)
class WatchTarget:
    """A resolved ``localFiles`` watch scope: what to scan, what to prune.

    Built once per watch session so the CLI command and the MCP server share
    one description of "what does this collection read from" instead of two
    copies that can drift.
    """

    collection: str
    base_path: str
    excluded_dirs: tuple[str, ...] = ()
    respect_gitignore: bool = True
    excluded_paths: tuple[Path, ...] = ()

    def scan(self) -> WatchSignature | None:
        """Fingerprint the tree; ``None`` keeps the data-loss gate intact."""
        return signature_for(
            self.base_path,
            excluded_dirs=self.excluded_dirs,
            respect_gitignore=self.respect_gitignore,
            excluded_paths=self.excluded_paths,
        )


def resolve_watch_target(
    collection: str,
    collections_path: str | Path,
    *,
    config_service: Any = None,
) -> WatchTarget | None:
    """Resolve ``collection``'s watch scope, or ``None`` when it cannot be watched.

    ``None`` covers both "no usable source path" and "not a directory" — callers
    report their own refusal message. The active storage root is pruned so a
    collection's own writes never wake its watcher (only relevant when the
    source tree contains the storage root; harmless otherwise).
    """
    from indexed.cli.knowledge.commands.update_service import (
        _read_manifest_reader_config,
    )

    reader_cfg = _read_manifest_reader_config(collection, str(collections_path))
    base_path = str(reader_cfg.get("basePath") or "")
    if not base_path or not Path(base_path).is_dir():
        return None

    excluded_paths: tuple[Path, ...] = ()
    if config_service is not None:
        try:
            storage_root = config_service.resolver.resolve_root(
                config_service.resolve_storage_mode()
            ).resolve()
            excluded_paths = (
                (storage_root / "data",)
                if storage_root == Path(base_path).resolve()
                else (storage_root,)
            )
        except Exception:  # noqa: BLE001 — an unresolvable root only costs extra scans
            excluded_paths = ()

    return WatchTarget(
        collection=collection,
        base_path=base_path,
        excluded_dirs=tuple(reader_cfg.get("excludedDirs") or ()),
        respect_gitignore=bool(reader_cfg.get("respectGitignore", True)),
        excluded_paths=excluded_paths,
    )


def run_watch_loop(
    *,
    scan: Callable[[], WatchSignature | None],
    apply_update: Callable[[], None],
    debounce_seconds: float,
    poll_interval_seconds: float,
    log_info: Callable[[str], None],
    log_error: Callable[[str], None],
    stop: threading.Event | None = None,
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Poll, coalesce a burst, then run exactly one update per quiet period.

    Returns a process exit code: 0 after a clean stop, 1 when the source path is
    unusable or ``max_consecutive_failures`` update passes failed in a row.
    """
    halt = stop if stop is not None else threading.Event()
    initial = scan()
    if initial is None:
        log_error("watched source path is not readable — nothing to watch")
        return 1

    last_applied: WatchSignature | None = None
    missing = False
    failures = 0
    first = True
    while not halt.is_set():
        if first:
            current = initial
        else:
            sleep(poll_interval_seconds)
            if halt.is_set():
                break
            current = scan()
        if current is None:
            if not missing:
                missing = True
                log_error(
                    "watched source path disappeared — keeping the last good index and "
                    "polling until it returns"
                )
            continue
        if missing:
            missing = False
            log_info("watched source path is back — resuming")
        if current == last_applied:
            continue

        # Absorb the burst: only a full quiet period of no further change runs an update.
        pending: WatchSignature | None = current
        deadline = clock() + (0 if first else debounce_seconds)
        first = False
        while not halt.is_set() and pending is not None:
            remaining = deadline - clock()
            if remaining <= 0:
                break
            sleep(min(poll_interval_seconds, remaining))
            observed = scan()
            if observed is None:
                pending = None
                missing = True
                log_error(
                    "watched source path disappeared mid-burst — last good index kept"
                )
                break
            if observed != pending:
                pending = observed
                deadline = clock() + debounce_seconds

        if halt.is_set() or pending is None or pending == last_applied:
            continue
        try:
            apply_update()
        except Exception as exc:  # noqa: BLE001 — surfaced as a logged failure, never a crash
            if scan() is None:
                if not missing:
                    missing = True
                    log_error(
                        "watched source path disappeared — keeping the last good index and "
                        "polling until it returns"
                    )
                continue
            failures += 1
            log_error(
                f"update pass failed ({failures}/{max_consecutive_failures}): {exc}"
            )
            if failures >= max_consecutive_failures:
                return 1
            continue

        failures = 0
        last_applied = pending
        log_info(f"updated collection from {pending.files} watched file(s)")

    return 0


__all__ = [
    "WatchSignature",
    "WatchTarget",
    "iter_watched_files",
    "resolve_watch_target",
    "signature_for",
    "run_watch_loop",
]
