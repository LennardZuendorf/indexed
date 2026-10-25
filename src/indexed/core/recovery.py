"""Recovery for collections stranded by an interrupted atomic swap (#126).

``core.v2.persist.replace_dir`` swaps a built staging directory into a
collection's canonical path in three steps::

    rename(<name>                 -> <name>.trash-<pid>)   # 1  old gen aside
    rename(<name>.tmp-<pid>-<hex> -> <name>)               # 2  new gen in
    rmtree(<name>.trash-<pid>)                             # 3  old gen gone

A process killed between (1) and (2) leaves NO canonical directory while BOTH
generations survive on disk under names discovery deliberately skips
(``_INTERNAL_COLLECTION_DIR_RE``), so a complete collection stays invisible
until someone moves directories by hand. This module resolves that state
deterministically on the next read (list / search / open), the choke point
every surface passes through.

Policy — never guess, never silently delete:

* A generation is COMPLETE only when its manifest is readable, declares
  ``version: "2"``, and its three ``storage/*.json`` files exist non-empty.
* Canonical complete → the strand is leftover cleanup: a ``.trash-`` sibling is
  removed (exactly what step 3 would have removed), a ``.tmp-`` sibling is
  quarantined (an unpublished build, preserved but never promoted).
* Canonical missing with a ``.trash-`` sibling → the swap was in flight: the
  newest complete generation is renamed back to the canonical name, the others
  are quarantined. Both generations are never mixed.
* Nothing complete → every strand is MOVED to ``<base>/.recovery/<name>/``
  (preserved, never deleted) and reported.
* Only a ``.tmp-`` sibling (no ``.trash-``) → rename 1 never ran, so the build
  was never published: quarantined, never promoted — an interrupted *new*
  collection must not surface as healthy.
* A strand whose manifest is readable but is not ``version: "2"`` (v1) is left
  untouched: v1 is frozen and outside this recovery path.

Quarantine lives under ``<base>/.recovery/``, which no discovery site treats as
a collection (it holds no ``manifest.json`` of its own) — so quarantining keeps
the data AND keeps discovery clean. Every step is a rename, so recovery is
cheap and idempotent: a second call finds nothing to do. Siblings whose
recorded pid is still alive are skipped, so a concurrent builder's staging
directory is never hijacked (one writer is still assumed overall).

This is NOT power-loss durability: the rename chain has no ``fsync``, so a
process crash is covered, a power cut with unflushed pages is not.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger

# ``<name>.tmp-<pid>-<hex>`` (build aside) and ``<name>.trash-<pid>`` (swap
# aside) — the transient names ``replace_dir`` creates. The digit run right
# after ``tmp``/``trash`` is the pid (``ingestion.create`` puts the pid FIRST so
# a letter-leading uuid hex can never escape the discovery-exclusion regex).
_STRANDED_DIR_RE = re.compile(
    r"^(?P<name>.+?)\.(?P<kind>tmp|trash)-(?P<pid>\d+)(?:-[0-9a-f]+)?$"
)

# Where unrecoverable strands are preserved (dot-prefixed: no discovery site
# reads it as a collection, and it carries no manifest.json of its own).
QUARANTINE_DIRNAME = ".recovery"

# Files ``StorageContext.persist`` writes for the only shipped vector store
# (``simple``). All three must exist for a generation to be loadable.
_V2_REQUIRED_STORAGE = (
    "docstore.json",
    "index_store.json",
    "default__vector_store.json",
)

_REASON_IN_FLIGHT = "an interrupted swap between the two renames left it aside"
_REASON_UNPUBLISHED = "an interrupted build was never swapped in"


@dataclass(frozen=True)
class StrandedGeneration:
    """One transient directory left behind by an interrupted swap."""

    path: Path
    name: str
    kind: str  # "tmp" (build aside) | "trash" (swap aside)
    pid: int
    v2: bool
    complete: bool


@dataclass(frozen=True)
class RecoveryOutcome:
    """What :func:`recover_stranded` did (and could not do) in one pass."""

    restored: tuple[tuple[str, Path], ...] = ()
    quarantined: tuple[tuple[str, Path], ...] = ()
    discarded: tuple[Path, ...] = ()
    # (collection name, why it could not be restored) — data is never deleted.
    unrecoverable: tuple[tuple[str, str], ...] = ()
    failures: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """True when this pass touched the filesystem."""
        return bool(self.restored or self.quarantined or self.discarded)

    def reason_for(self, name: str) -> Optional[str]:
        """Why ``name`` could not be restored, or ``None`` if it was / was not
        stranded at all."""
        for blocked, reason in self.unrecoverable:
            if blocked == name:
                return reason
        return None


def recover_stranded(
    base: Path, *, names: Optional[Iterable[str]] = None
) -> RecoveryOutcome:
    """Resolve stranded ``.tmp-``/``.trash-`` generations under ``base``.

    Args:
        base: the collections directory.
        names: restrict recovery to these collection names (an explicit
            open/search request); ``None`` sweeps every stranded name.

    Returns:
        A :class:`RecoveryOutcome` naming everything restored, quarantined,
        removed or left unrecoverable. Never raises for filesystem trouble —
        a failure is recorded and logged instead, so a read path can recover
        best-effort without masking the actual operation.
    """
    base = Path(base)
    if not base.is_dir():
        return RecoveryOutcome()

    wanted = set(names) if names is not None else None
    acc = _Accumulator()
    for name, generations in sorted(_stranded_generations(base).items()):
        if wanted is not None and name not in wanted:
            continue
        _recover_collection(base, name, generations, acc)

    return RecoveryOutcome(
        restored=tuple(acc.restored),
        quarantined=tuple(acc.quarantined),
        discarded=tuple(acc.discarded),
        unrecoverable=tuple(acc.unrecoverable),
        failures=tuple(acc.failures),
    )


class _Accumulator:
    """Record + perform the three recovery actions, logging each one."""

    def __init__(self) -> None:
        self.restored: list[tuple[str, Path]] = []
        self.quarantined: list[tuple[str, Path]] = []
        self.discarded: list[Path] = []
        self.unrecoverable: list[tuple[str, str]] = []
        self.failures: list[str] = []

    def promote(self, name: str, source: Path, canonical: Path, reason: str) -> bool:
        """Rename a complete generation back to its canonical name."""
        try:
            os.rename(source, canonical)
        except OSError as exc:
            self._fail(
                f"could not restore {str(source)!r} to {str(canonical)!r}: {exc}"
            )
            return False
        self.restored.append((name, canonical))
        logger.warning(
            f"collection recovery: restored '{name}' from {str(source)!r} "
            f"({reason}); it is discoverable again"
        )
        return True

    def quarantine(self, base: Path, name: str, source: Path, reason: str) -> None:
        """Move a strand (or an incomplete canonical dir) to ``.recovery``."""
        try:
            root = base / QUARANTINE_DIRNAME / name
            target = _free_target(root / source.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(source, target)
        except OSError as exc:
            self._fail(f"could not quarantine {str(source)!r}: {exc}")
            return
        _note(target.parent, f"quarantined {source.name} -> {target.name}: {reason}")
        self.quarantined.append((name, target))
        logger.warning(
            f"collection recovery: quarantined {str(source)!r} -> {str(target)!r} "
            f"({reason})"
        )

    def discard(self, path: Path, name: str, reason: str) -> None:
        """Remove a strand proven redundant by a complete canonical directory."""
        shutil.rmtree(path, ignore_errors=True)
        if path.exists():
            self._fail(
                f"leftover {str(path)!r} could not be removed ({reason}); "
                f"collection '{name}' itself is intact"
            )
            return
        self.discarded.append(path)
        logger.info(
            f"collection recovery: removed leftover {str(path)!r} "
            f"({reason}; collection '{name}' is intact)"
        )

    def block(self, name: str, reason: str) -> None:
        """Record a name that could not be restored (its data is preserved)."""
        self.unrecoverable.append((name, reason))
        logger.warning(
            f"collection recovery: '{name}' could not be restored ({reason}); "
            f"its data is preserved under {str(QUARANTINE_DIRNAME)!r}"
        )

    def _fail(self, message: str) -> None:
        self.failures.append(message)
        logger.error(f"collection recovery: {message}")


def _recover_collection(
    base: Path,
    name: str,
    generations: list[StrandedGeneration],
    acc: _Accumulator,
) -> None:
    """Apply the recovery policy for one collection name."""
    relevant = [gen for gen in generations if gen.v2]
    if not relevant:
        # No v2 generation (v1 collections are frozen / out of scope), or a
        # manifest that never became readable — nothing provable to restore.
        logger.debug(
            f"collection recovery: leaving {len(generations)} non-v2 strand(s) "
            f"of '{name}' untouched"
        )
        return

    canonical = base / name
    complete = sorted(
        (gen for gen in relevant if gen.complete),
        key=_newest_first,
        reverse=True,
    )

    if canonical.is_dir():
        if _is_complete(canonical):
            # Canonical is complete: the strands are leftover cleanup from a
            # swap that did finish. The trash is provably superseded; a staging
            # dir is an unpublished build and is preserved, not deleted.
            for gen in relevant:
                if gen.kind == "trash":
                    acc.discard(
                        gen.path, name, "the swap that would have removed it completed"
                    )
                else:
                    acc.quarantine(
                        base,
                        name,
                        gen.path,
                        "unpublished build beside a complete collection",
                    )
            return
        if complete:
            # A broken canonical directory with a complete generation beside
            # it: preserve the broken one, put the good one back in place.
            acc.quarantine(
                base, name, canonical, "incomplete, replaced by a complete generation"
            )
            _restore_and_quarantine(
                base, name, relevant, complete, canonical, acc, _REASON_IN_FLIGHT
            )
            return
        acc.block(
            name,
            "the collection directory is incomplete and no complete "
            "generation survives",
        )
        return
    # Canonical missing: the interesting case — a crash between the renames.
    if not complete:
        for gen in relevant:
            acc.quarantine(base, name, gen.path, "no complete generation to restore")
        acc.block(
            name,
            "the collection directory is missing and no complete generation survives",
        )
        return

    if not any(gen.kind == "trash" for gen in relevant):
        # Rename 1 never ran, so nothing was ever published for this name.
        for gen in relevant:
            acc.quarantine(base, name, gen.path, _REASON_UNPUBLISHED)
        acc.block(name, _REASON_UNPUBLISHED)
        return

    _restore_and_quarantine(
        base, name, relevant, complete, canonical, acc, _REASON_IN_FLIGHT
    )


def _restore_and_quarantine(
    base: Path,
    name: str,
    relevant: list[StrandedGeneration],
    complete: list[StrandedGeneration],
    canonical: Path,
    acc: _Accumulator,
    reason: str,
) -> None:
    """Promote the newest complete generation, quarantine every other strand."""
    best = complete[0]
    if not acc.promote(name, best.path, canonical, reason):
        return
    for gen in relevant:
        if gen.path == best.path:
            continue
        acc.quarantine(
            base, name, gen.path, f"superseded by the restored generation ({reason})"
        )


def _newest_first(gen: StrandedGeneration) -> tuple[float, int]:
    """Sort key: newer manifest wins; a newer *build* (``tmp``) beats an old gen."""
    try:
        built = (gen.path / "manifest.json").stat().st_mtime
    except OSError:
        built = 0.0
    return (built, 1 if gen.kind == "tmp" else 0)


def _stranded_generations(base: Path) -> dict[str, list[StrandedGeneration]]:
    """Group the ``.tmp-``/``.trash-`` siblings under ``base`` by collection name."""
    groups: dict[str, list[StrandedGeneration]] = {}
    try:
        children = sorted(base.iterdir())
    except OSError:
        return groups
    for child in children:
        match = _STRANDED_DIR_RE.match(child.name)
        if match is None or not child.is_dir():
            continue
        pid = int(match.group("pid"))
        if _pid_alive(pid):
            # A live writer owns this staging/trash dir right now — hands off.
            logger.debug(
                f"collection recovery: skipping {str(child)!r}, its writer "
                f"(pid {pid}) is still running"
            )
            continue
        manifest = _manifest(child)
        is_v2 = manifest is not None and manifest.get("version") == "2"
        groups.setdefault(match.group("name"), []).append(
            StrandedGeneration(
                path=child,
                name=match.group("name"),
                kind=match.group("kind"),
                pid=pid,
                v2=is_v2,
                complete=is_v2 and _storage_complete(child),
            )
        )
    return groups


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness probe for the pid embedded in a strand's name."""
    if pid == os.getpid():
        # Our own pid cannot own a strand we are about to sweep: it is a
        # recycled pid from a dead process.
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):
        return False
    except OSError:
        return True
    return True


def _manifest(directory: Path) -> Optional[dict]:
    """The parsed manifest of a generation, or ``None`` when unreadable."""
    try:
        raw = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _storage_complete(directory: Path) -> bool:
    """True when every required ``storage/*.json`` file exists and is non-empty."""
    storage = directory / "storage"
    for filename in _V2_REQUIRED_STORAGE:
        path = storage / filename
        try:
            if not path.is_file() or path.stat().st_size == 0:
                return False
        except OSError:
            return False
    return True


def _is_complete(directory: Path) -> bool:
    """True when ``directory`` holds a complete v2 generation."""
    manifest = _manifest(directory)
    if manifest is None or manifest.get("version") != "2":
        return False
    return _storage_complete(directory)


def _free_target(target: Path) -> Path:
    """A not-yet-existing path next to ``target`` (never overwrite a quarantine)."""
    if not target.exists():
        return target
    counter = 1
    while True:
        candidate = target.with_name(f"{target.name}-{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def _note(root: Path, line: str) -> None:
    """Append one line to the quarantine's operator log (best effort)."""
    try:
        with (root / "recovery.log").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:  # pragma: no cover - diagnostics must never break recovery
        pass


__all__ = [
    "QUARANTINE_DIRNAME",
    "RecoveryOutcome",
    "StrandedGeneration",
    "recover_stranded",
]
