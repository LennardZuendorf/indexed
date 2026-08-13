"""Crash-safe directory swap for the v2 build-aside create path (core-v2/2c).

``core/v2`` may not import v1's ``DiskPersister`` (import rule core/v2 ↛ core.v1;
v1 is frozen). :func:`replace_dir` REIMPLEMENTS the exact crash-safe semantics of
``DiskPersister.replace_folder`` (v1-surface-map §7): the destination is only ever
removed AFTER the fully-built replacement already exists on disk, so a crash
mid-swap never leaves neither version present, and a failed swap rolls the
original back into place (fixes the PR #86 delete-before-persist defect).

A future consolidation into ``utils`` is possible; v1 is frozen so the two
cannot share the implementation now — this intentionally mirrors it instead.
No third-party or LlamaIndex import: pure ``os``/``shutil``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from loguru import logger


def replace_dir(staging: Path, dest: Path) -> None:
    """Atomically swap the built ``staging`` dir into ``dest``'s place.

    If ``dest`` already exists it is first moved aside to ``dest.trash-<pid>``
    (a cheap rename, not a copy) so BOTH the old and the new data are present
    on disk simultaneously until the final rename; the trash copy is removed
    only after the swap succeeds. If the swap rename fails, the moved-aside
    original is renamed back so the ORIGINAL collection is restored, then the
    error re-raises. When ``dest`` does not exist, the staging dir is renamed
    straight into place.
    """
    staging = Path(staging)
    dest = Path(dest)

    if dest.exists():
        trash = dest.with_name(f"{dest.name}.trash-{os.getpid()}")
        os.rename(dest, trash)
        try:
            os.rename(staging, dest)
        except Exception as swap_error:
            try:
                os.rename(trash, dest)
            except OSError as rollback_error:
                logger.warning(
                    f"replace_dir rollback failed after swap error "
                    f"({swap_error!r}): original collection may be stranded at "
                    f"{str(trash)!r} and the built replacement at "
                    f"{str(staging)!r} ({rollback_error!r})"
                )
            else:
                logger.warning(
                    f"replace_dir swap failed ({swap_error!r}); rolled back "
                    f"{dest.name!r} to its original contents, but the built "
                    f"replacement remains stranded at {str(staging)!r}"
                )
            raise
        shutil.rmtree(trash, ignore_errors=True)
        if trash.exists():
            logger.warning(
                f"replace_dir: residual trash directory left behind at {str(trash)!r}"
            )
    else:
        os.rename(staging, dest)


__all__ = ["replace_dir"]
