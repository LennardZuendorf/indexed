#!/usr/bin/env python3
"""Rebuild the pinned retrieval-eval corpus + manifest (issue #204).

The corpus is a *copy*, not a reference: the eval must measure the same bytes
forever, so a doc edit in the repo cannot silently move the baseline. Run this
only when you deliberately want a new corpus revision — and commit the resulting
``eval/corpus/`` and ``eval/corpus.json`` together with a regenerated baseline.

    uv run python scripts/build_eval_corpus.py           # rebuild in place
    uv run python scripts/build_eval_corpus.py --check    # drift check, no writes
    uv run python scripts/build_eval_corpus.py --rev HEAD # pin another revision

Provenance: Git inputs come from the selected revision. Authored sanitized
extracts are read from local snapshot inputs and retain their separate capture
metadata and input hashes in ``eval/corpus.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from indexed.eval.cases import EvalDataError, corpus_revision

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
    "src/indexed/core/recovery.py": "recovery-code.py",
    "src/indexed/core/v2/config_models.py": "v2-config-code.py",
    "src/indexed/core/v2/services/__init__.py": "v2-service-code.py",
}

LOCAL_SNAPSHOTS = {
    "eval/sources/github-issue-126.md": "github-issue-126.md",
    "eval/sources/github-pr-244.md": "github-pr-244.md",
}


def git_rev(rev: str) -> str:
    """Resolve a commit revision or stop before producing corpus artifacts."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"invalid git revision: {rev}") from exc
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


def local_snapshot(source: str, name: str) -> tuple[bytes, dict]:
    """Read authored capture bytes without attributing them to the Git revision."""
    metadata_path = REPO_ROOT / "eval/sources/provenance.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        entry = metadata[name]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"cannot read snapshot provenance for {name}: {exc}") from exc
    if not isinstance(entry, dict):
        raise SystemExit(f"snapshot provenance for {name} must be an object")
    fields = (
        "upstream_url",
        "captured_revision",
        "captured_at",
        "sanitization_notes",
        "input_sha256",
    )
    for field in fields:
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise SystemExit(f"{name}: missing or invalid {field}")
    upstream = urlparse(entry["upstream_url"])
    if upstream.scheme != "https" or not upstream.netloc:
        raise SystemExit(f"{name}: invalid upstream_url")
    try:
        captured = datetime.fromisoformat(entry["captured_at"].replace("Z", "+00:00"))
        if captured.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise SystemExit(f"{name}: invalid captured_at") from exc
    try:
        payload = (REPO_ROOT / source).read_bytes()
    except OSError as exc:
        raise SystemExit(f"cannot read local snapshot {source}: {exc}") from exc
    if hashlib.sha256(payload).hexdigest() != entry["input_sha256"]:
        raise SystemExit(f"{name}: input_sha256 does not match local snapshot bytes")
    return payload, {field: entry[field] for field in fields}


def build_inputs(rev: str) -> tuple[dict, dict[str, bytes]]:
    """Assemble pinned Git and verified snapshot bytes with their manifest hashes."""
    files = []
    lines = []
    payloads = {}
    for source, name in {**SOURCES, **LOCAL_SNAPSHOTS}.items():
        if source in LOCAL_SNAPSHOTS:
            payload, provenance = local_snapshot(source, name)
            provenance.update(source_kind="local_snapshot", source_path=source)
        else:
            payload = source_bytes(source, rev)
            provenance = {"source_kind": "git"}
        digest = hashlib.sha256(payload).hexdigest()
        files.append(
            {
                "path": name,
                "source": source,
                **provenance,
                "sha256": digest,
                "bytes": len(payload),
            }
        )
        payloads[name] = payload
        lines.append(f"{digest}  {name}\n")
    tree = hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA,
        "corpus_id": CORPUS_ID,
        "source_repo_rev": rev,
        "tree_sha256": tree,
        "files": files,
    }, payloads


def build_manifest(rev: str = "HEAD") -> dict:
    return build_inputs(git_rev(rev))[0]


def check_corpus(rev: str) -> int:
    """Fail on pinned corpus drift and report current source changes as advisory."""
    try:
        pinned = corpus_revision(CORPUS_DIR, MANIFEST)
    except EvalDataError as exc:
        print(f"drift: {exc}", file=sys.stderr)
        return 1
    current = {entry["path"]: entry["sha256"] for entry in pinned["files"]}
    changed = []
    for source, name in {**SOURCES, **LOCAL_SNAPSHOTS}.items():
        try:
            payload = (
                local_snapshot(source, name)[0]
                if source in LOCAL_SNAPSHOTS
                else source_bytes(source, rev)
            )
        except SystemExit as exc:
            print(f"note: current source unavailable: {exc}")
            changed.append(name)
            continue
        if hashlib.sha256(payload).hexdigest() != current.get(name):
            changed.append(name)
    changed.extend(set(current) - set(SOURCES.values()) - set(LOCAL_SNAPSHOTS.values()))
    if changed:
        print(f"note: repo sources changed since pinning: {', '.join(sorted(changed))}")
    print("corpus is pinned and unchanged")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Validate the pinned corpus or rebuild its bytes and manifest from verified inputs."""
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

    revision = git_rev(args.rev)
    if args.check:
        return check_corpus(revision)

    manifest, payloads = build_inputs(revision)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (CORPUS_DIR / name).write_bytes(payload)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(manifest['files'])} files to {CORPUS_DIR.relative_to(REPO_ROOT)}"
    )
    print(f"tree_sha256 {manifest['tree_sha256']}")
    print(f"source_repo_rev {manifest['source_repo_rev']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
