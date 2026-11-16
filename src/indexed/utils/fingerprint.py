"""One definition of "the same file" — for change tracking and the LSP.

The indexer decides what changed by comparing a fingerprint it recorded on its
last run against the file on disk; the language server decides whether a file's
index entry is stale by comparing the very same two things. If the two computed
it differently, the editor could call a file stale that the indexer considers
current (or the reverse), and a diagnostics channel that disagrees with the
indexer is exactly the kind of noise issue #241 refuses to ship.

Leaf-layer on purpose: stdlib plus ``xxhash`` only, so both the file connector
and the top-layer presentation surfaces may import it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

#: A file's ``(xxh64 hex digest, size in bytes)``.
Fingerprint = Tuple[str, int]


def file_fingerprint(path: str) -> Optional[Fingerprint]:
    """The fingerprint of the bytes at ``path``, or ``None`` if unreadable.

    ``None`` means *no opinion* — never "unchanged". A caller that cannot read
    the file must stay silent rather than report a difference it cannot see.
    """
    import xxhash  # lazy: only the indexing and diagnostics paths need it

    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return xxhash.xxh64(data).hexdigest(), len(data)


__all__ = ["Fingerprint", "file_fingerprint"]
