#!/usr/bin/env python3
"""Rebuild the pinned retrieval-eval corpus + manifest (issue #204).

The corpus is a *copy*, not a reference: the eval must measure the same bytes
forever, so a doc edit in the repo cannot silently move the baseline. Run this
only when you deliberately want a new corpus revision — and commit the resulting
``eval/corpus/`` and ``eval/corpus.json`` together with a regenerated baseline.

    uv run python scripts/build_eval_corpus.py           # rebuild in place
    uv run python scripts/build_eval_corpus.py --check    # drift check, no writes
    uv run python scripts/build_eval_corpus.py --rev HEAD # pin another revision

Provenance: every entry records the repo file it came from, so a reader of
``eval/corpus.json`` can trace each document back without trusting the copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "eval" / "corpus"
MANIFEST = REPO_ROOT / "eval" / "corpus.json"
SCHEMA = "indexed.eval.corpus.v1"
CORPUS_ID = "indexed-docs"

#: Repo file -> pinned corpus name. Flat names, no dot-directories: the files
#: connector does not promise to walk hidden trees, and a flat corpus keeps the
#: document ids in the case set readable.
#: ``AGENTS.md`` is pinned as ``agents-doc.md`` so the corpus copy does not trip
#: the one-real-AGENTS.md size gate (`scripts/check_sizes.py`); the manifest's
#: ``source`` keeps the provenance unambiguous.
SOURCES = {
    "README.md": "README.md",
    "AGENTS.md": "agents-doc.md",
    ".spec/product.md": "product.md",
    ".spec/plan.md": "plan.md",
    ".spec/tech.md": "tech.md",
    ".spec/tech-app.md": "tech-app.md",
    ".spec/tech-config.md": "tech-config.md",
    ".spec/tech-connectors.md": "tech-connectors.md",
    ".spec/tech-core.md": "tech-core.md",
    ".spec/tech-parsing.md": "tech-parsing.md",
    ".spec/lessons.md": "lessons.md",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def git_rev(rev: str) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", rev],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def source_bytes(source: str, rev: str) -> bytes:
    """The pinned bytes of ``source`` at ``rev`` — read from git, not the worktree.

    Copying the working tree while recording ``HEAD`` would let an uncommitted doc
    edit land in the corpus under a revision that does not contain it.
    """
    out = subprocess.run(
        ["git", "show", f"{rev}:{source}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if out.returncode != 0:
        raise SystemExit(f"cannot read {source} at {rev}: git show failed")
    return out.stdout


def build_manifest(rev: str = "HEAD") -> dict:
    files = []
    lines = []
    for source, name in SOURCES.items():
        payload = source_bytes(source, rev)
        digest = hashlib.sha256(payload).hexdigest()
        files.append(
            {
                "path": name,
                "source": source,
                "sha256": digest,
                "bytes": len(payload),
            }
        )
        lines.append(f"{digest}  {name}\n")
    tree = hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA,
        "corpus_id": CORPUS_ID,
        "source_repo_rev": git_rev(rev),
        "tree_sha256": tree,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the pinned corpus matches the manifest; write nothing",
    )
    parser.add_argument(
        "--rev",
        default="HEAD",
        help="git revision to pin the corpus from (default: HEAD)",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest(args.rev)

    if args.check:
        if not MANIFEST.is_file():
            print(f"drift: {MANIFEST} is missing", file=sys.stderr)
            return 1
        current = json.loads(MANIFEST.read_text(encoding="utf-8"))
        expected = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
        pinned = {entry["path"]: entry["sha256"] for entry in current["files"]}

        # 1. The pinned copy must match the manifest — that is what a report claims
        #    to have measured, so any difference is a failure.
        drifted = sorted(
            name
            for name in set(expected) | set(pinned)
            if (CORPUS_DIR / name).is_file()
            and sha256_file(CORPUS_DIR / name) != pinned.get(name)
        )
        missing = sorted(name for name in pinned if not (CORPUS_DIR / name).is_file())
        if drifted or missing:
            if missing:
                print(f"missing pinned files: {', '.join(missing)}", file=sys.stderr)
            if drifted:
                print(f"pinned copy drifted: {', '.join(drifted)}", file=sys.stderr)
            return 1

        # 2. Repo sources moving on is normal (docs keep changing); it only means the
        #    corpus is a snapshot of an older revision, which the manifest records.
        moved = sorted(
            name
            for name in set(expected) | set(pinned)
            if expected.get(name) != pinned.get(name)
        )
        if moved:
            print(f"note: repo sources changed since pinning: {', '.join(moved)}")
        print("corpus is pinned and unchanged")
        return 0

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for source, name in SOURCES.items():
        (CORPUS_DIR / name).write_bytes(source_bytes(source, args.rev))
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(manifest['files'])} files to {CORPUS_DIR.relative_to(REPO_ROOT)}"
    )
    print(f"tree_sha256 {manifest['tree_sha256']}")
    print(f"source_repo_rev {manifest['source_repo_rev']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
