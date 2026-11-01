"""Pinned eval case set + pinned corpus manifest (issue #204).

Two committed JSON files carry the judgement, so the numbers in
``eval/baseline.json`` are reproducible by anyone:

* ``eval/cases.json`` — one record per case: the query, its provenance (where
  the query came from — real GitHub issue titles, never invented ones), the
  expected document ids, the near-miss distractors, and the relevance rationale
  with the anchor that justifies it.
* ``eval/corpus.json`` — the pinned corpus: each file's ``sha256`` plus the
  ``tree_sha256`` over all of them, so a report can name the exact corpus it
  measured.

Plain dataclasses rather than pydantic: the loaders are the validation surface,
and they raise actionable messages instead of a raw ``ValidationError`` stack.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

CASES_SCHEMA = "indexed.eval.cases.v1"
CORPUS_SCHEMA = "indexed.eval.corpus.v1"

#: Default locations, relative to the repository root.
DEFAULT_CASES_PATH = Path("eval/cases.json")
DEFAULT_CORPUS_DIR = Path("eval/corpus")
DEFAULT_CORPUS_MANIFEST = Path("eval/corpus.json")


class EvalDataError(ValueError):
    """A pinned eval artifact is missing, malformed, or drifted."""


@dataclass(frozen=True)
class Case:
    """One judged query: what to ask, what should come back, and why."""

    id: str
    query: str
    provenance: str
    rationale: str
    relevant: List[str] = field(default_factory=list)
    distractors: List[str] = field(default_factory=list)
    answered_by: str = ""

    @property
    def answerable(self) -> bool:
        return bool(self.relevant)


@dataclass(frozen=True)
class CaseSet:
    """The committed case set, plus the revision hash that pins it."""

    schema: str
    description: str
    corpus_id: str
    cases: List[Case]
    sha256: str

    @property
    def ids(self) -> List[str]:
        """Return case identifiers in their committed order."""
        return [case.id for case in self.cases]


def _sha256_file(path: Path) -> str:
    """Hash file bytes in bounded blocks without loading the whole file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    """Raise EvalDataError when an artifact contract is violated."""
    if not condition:
        raise EvalDataError(message)


def _load_object(path: Path) -> Dict[str, Any]:
    """Read a JSON object and wrap unreadable or malformed input as EvalDataError."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalDataError(f"{path}: cannot read JSON: {exc}") from exc
    _require(isinstance(raw, dict), f"{path}: top level must be an object")
    return raw


def _text(value: Any) -> bool:
    """Accept strings containing at least one non-whitespace character."""
    return isinstance(value, str) and bool(value.strip())


def _flat_name(value: Any, where: str) -> str:
    """Validate a flat document name and return its case-insensitive identity."""
    _require(
        _text(value)
        and value == value.strip()
        and value not in {".", ".."}
        and not any(char in value for char in "/\\:\x00"),
        f"{where}: expected a flat document path",
    )
    return value.lower()


def _hash(value: Any) -> bool:
    """Accept only lowercase hexadecimal SHA-256 digests."""
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load_case_set(path: Optional[Path] = None) -> CaseSet:
    """Load + validate ``eval/cases.json``.

    Validation is deliberately strict: a duplicate case id, an empty query, a
    case that is neither answerable nor marked unanswerable, or a missing
    rationale all mean the judgement is not reproducible and the run is refused.
    """
    path = Path(path) if path is not None else DEFAULT_CASES_PATH
    if not path.is_file():
        raise EvalDataError(f"case set not found: {path}")
    raw = _load_object(path)

    _require(
        raw.get("schema") == CASES_SCHEMA,
        f"{path}: expected schema {CASES_SCHEMA!r}, got {raw.get('schema')!r}",
    )
    _require(isinstance(raw.get("cases"), list), f"{path}: cases must be a list")
    _require(bool(raw["cases"]), f"{path}: case set is empty")
    _require(_text(raw.get("corpus_id")), f"{path}: missing 'corpus_id'")
    _require(
        isinstance(raw.get("description", ""), str),
        f"{path}: description must be a string",
    )

    cases: List[Case] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw["cases"]):
        where = f"{path}: cases[{index}]"
        _require(isinstance(entry, dict), f"{where}: must be an object")
        case_id = entry.get("id")
        _require(
            _text(case_id) and case_id == case_id.strip(),
            f"{where}: missing 'id'",
        )
        _require(case_id not in seen, f"{where}: duplicate id {case_id!r}")
        seen.add(case_id)
        _require(
            isinstance(entry.get("query"), str) and bool(entry["query"].strip()),
            f"{where} ({case_id}): missing 'query'",
        )
        _require(
            isinstance(entry.get("provenance"), str)
            and bool(entry["provenance"].strip()),
            f"{where} ({case_id}): missing 'provenance' — every query needs an "
            "origin, no invented queries",
        )
        _require(
            isinstance(entry.get("rationale"), str)
            and bool(entry["rationale"].strip()),
            f"{where} ({case_id}): missing 'rationale' — relevance must be "
            "arguable against the corpus",
        )
        relevant = entry.get("relevant", [])
        distractors = entry.get("distractors", [])
        _require(
            isinstance(relevant, list) and isinstance(distractors, list),
            f"{where} ({case_id}): 'relevant'/'distractors' must be lists",
        )
        _require(
            all(isinstance(doc, str) and doc.strip() for doc in relevant + distractors),
            f"{where} ({case_id}): 'relevant'/'distractors' entries must be "
            "non-empty document names",
        )
        _require(
            bool(relevant) or bool(distractors),
            f"{where} ({case_id}): an unanswerable case needs at least one "
            "distractor, or it measures nothing",
        )
        canonical_relevant = [_flat_name(doc, where) for doc in relevant]
        canonical_distractors = [_flat_name(doc, where) for doc in distractors]
        for names in (canonical_relevant, canonical_distractors):
            _require(
                len(names) == len(set(names)), f"{where}: duplicate document identity"
            )
        overlap = set(canonical_relevant) & set(canonical_distractors)
        _require(
            not overlap,
            f"{where} ({case_id}): {sorted(overlap)} listed as both relevant "
            "and distractor",
        )
        _require(
            isinstance(entry.get("answered_by", ""), str),
            f"{where}: answered_by must be a string",
        )
        cases.append(
            Case(
                id=case_id,
                query=entry["query"],
                provenance=entry["provenance"],
                rationale=entry["rationale"],
                relevant=list(relevant),
                distractors=list(distractors),
                answered_by=entry.get("answered_by", ""),
            )
        )

    return CaseSet(
        schema=CASES_SCHEMA,
        description=raw.get("description", ""),
        corpus_id=raw.get("corpus_id", ""),
        cases=cases,
        sha256=_sha256_file(path),
    )


def corpus_revision(
    corpus_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    *,
    verify: bool = True,
) -> Dict[str, Any]:
    """Hash the pinned corpus and check it against ``eval/corpus.json``.

    ``tree_sha256`` is the hash over ``"<sha256>  <name>\\n"`` lines sorted by
    name — cheap to recompute anywhere, and it changes if any byte of any pinned
    file changes. With ``verify`` the on-disk corpus must match the manifest, so
    a report can never claim a revision it did not measure.
    """
    corpus_dir = Path(corpus_dir) if corpus_dir is not None else DEFAULT_CORPUS_DIR
    manifest_path = (
        Path(manifest_path) if manifest_path is not None else DEFAULT_CORPUS_MANIFEST
    )
    if not corpus_dir.is_dir():
        raise EvalDataError(f"corpus directory not found: {corpus_dir}")
    if not manifest_path.is_file():
        raise EvalDataError(f"corpus manifest not found: {manifest_path}")

    manifest = _load_object(manifest_path)
    _require(
        manifest.get("schema") == CORPUS_SCHEMA,
        f"{manifest_path}: expected schema {CORPUS_SCHEMA!r}",
    )
    for key in ("corpus_id", "source_repo_rev"):
        _require(_text(manifest.get(key)), f"{manifest_path}: missing '{key}'")
    _require(
        _hash(manifest.get("tree_sha256")), f"{manifest_path}: invalid tree_sha256"
    )
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise EvalDataError(f"{manifest_path}: files must be a non-empty list")
    identities: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{manifest_path}: files[{index}]"
        _require(isinstance(entry, dict), f"{where}: must be an object")
        name = _flat_name(entry.get("path"), where)
        _require(name not in identities, f"{where}: duplicate document path {name!r}")
        identities.add(name)
        _require(_hash(entry.get("sha256")), f"{where}: invalid sha256")
        _require(
            type(entry.get("bytes")) is int and entry["bytes"] >= 0,
            f"{where}: invalid bytes",
        )
        _require(_text(entry.get("source")), f"{where}: invalid source")

    files: List[Dict[str, Any]] = []
    lines: List[str] = []
    pinned = {entry["path"] for entry in entries}
    for path in corpus_dir.iterdir():
        _require(
            stat.S_ISREG(path.lstat().st_mode),
            f"corpus entry is not a regular file: {path}",
        )
        _require(
            path.name in pinned,
            f"corpus directory holds files the manifest does not pin: {path.name}",
        )
    for entry in manifest["files"]:
        name = entry["path"]
        path = corpus_dir / name
        if not path.exists():
            raise EvalDataError(f"pinned corpus file missing: {path}")
        actual = _sha256_file(path)
        if verify and actual != entry["sha256"]:
            raise EvalDataError(
                f"pinned corpus drift: {path} is {actual}, manifest says "
                f"{entry['sha256']} — regenerate corpus.json deliberately if the "
                "corpus really changed"
            )
        _require(
            not verify or path.stat().st_size == entry["bytes"],
            f"{manifest_path}: bytes mismatch for {name}",
        )
        files.append({**entry, "sha256": actual, "bytes": path.stat().st_size})
        lines.append(f"{actual}  {name}\n")

    tree = hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()
    _require(
        not verify or tree == manifest["tree_sha256"],
        f"{manifest_path}: tree_sha256 drift",
    )
    return {
        "corpus_id": manifest.get("corpus_id", ""),
        "source_repo_rev": manifest.get("source_repo_rev", ""),
        "tree_sha256": tree,
        "files": files,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write a report/case artifact the way the harness commits it: 2-space, stable key order."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
