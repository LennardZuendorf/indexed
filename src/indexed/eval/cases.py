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
        return [case.id for case in self.cases]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalDataError(message)


def load_case_set(path: Optional[Path] = None) -> CaseSet:
    """Load + validate ``eval/cases.json``.

    Validation is deliberately strict: a duplicate case id, an empty query, a
    case that is neither answerable nor marked unanswerable, or a missing
    rationale all mean the judgement is not reproducible and the run is refused.
    """
    path = Path(path) if path is not None else DEFAULT_CASES_PATH
    if not path.is_file():
        raise EvalDataError(f"case set not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))

    _require(
        raw.get("schema") == CASES_SCHEMA,
        f"{path}: expected schema {CASES_SCHEMA!r}, got {raw.get('schema')!r}",
    )
    _require(bool(raw.get("cases")), f"{path}: case set is empty")

    cases: List[Case] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw["cases"]):
        where = f"{path}: cases[{index}]"
        case_id = entry.get("id")
        _require(
            isinstance(case_id, str) and bool(case_id),
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
        relevant = entry.get("relevant") or []
        distractors = entry.get("distractors") or []
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
        overlap = set(relevant) & set(distractors)
        _require(
            not overlap,
            f"{where} ({case_id}): {sorted(overlap)} listed as both relevant "
            "and distractor",
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

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(
        manifest.get("schema") == CORPUS_SCHEMA,
        f"{manifest_path}: expected schema {CORPUS_SCHEMA!r}",
    )

    files: List[Dict[str, Any]] = []
    lines: List[str] = []
    pinned = [entry["path"] for entry in manifest["files"]]
    for entry in manifest["files"]:
        name = entry["path"]
        path = corpus_dir / name
        if not path.is_file():
            raise EvalDataError(f"pinned corpus file missing: {path}")
        actual = _sha256_file(path)
        if verify and actual != entry["sha256"]:
            raise EvalDataError(
                f"pinned corpus drift: {path} is {actual}, manifest says "
                f"{entry['sha256']} — regenerate corpus.json deliberately if the "
                "corpus really changed"
            )
        files.append(
            {"path": name, "sha256": actual, "source": entry.get("source", "")}
        )
        lines.append(f"{actual}  {name}\n")

    # The tree hash covers the pinned names only, so an unpinned file sitting in
    # the corpus directory would be indexed without moving the revision the
    # report claims to have measured.
    unpacked = sorted(
        path.name
        for path in corpus_dir.iterdir()
        if path.is_file() and path.name not in set(pinned)
    )
    if unpacked:
        raise EvalDataError(
            f"corpus directory holds files the manifest does not pin: {unpacked} "
            "— remove them, or pin them via scripts/build_eval_corpus.py"
        )

    tree = hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()
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
