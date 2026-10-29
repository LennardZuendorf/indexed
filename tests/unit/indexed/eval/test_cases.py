"""Pinned case-set + corpus-manifest loading and drift refusal (issue #204)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from indexed.eval.cases import (
    EvalDataError,
    corpus_revision,
    load_case_set,
    write_json,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _minimal_case(**overrides) -> dict:
    case = {
        "id": "c1",
        "query": "a real query",
        "provenance": "GitHub issue #1 title",
        "rationale": "because the document says so",
        "relevant": ["plan.md"],
    }
    case.update(overrides)
    return case


def _case_set(cases, **top) -> dict:
    payload = {"schema": "indexed.eval.cases.v1", "cases": cases}
    payload.update(top)
    return payload


_ANCHOR_RE = re.compile(r"^(?:(?P<file>[\w.\-]+):)?(?P<start>\d+)(?:-(?P<end>\d+))?$")


def _anchors(answered_by: str) -> list[tuple[str, int, int]]:
    """Parse ``answered_by`` into ``(file, first_line, last_line)`` triples.

    The committed form is ``file:12, 34-56, other.md:7`` — a bare number keeps the
    file of the previous anchor, and a range is inclusive.
    """
    anchors: list[tuple[str, int, int]] = []
    current = ""
    for part in (piece.strip() for piece in answered_by.split(",")):
        if not part:
            continue
        match = _ANCHOR_RE.match(part)
        if match is None:
            raise ValueError(f"unparseable anchor {part!r} in {answered_by!r}")
        current = match["file"] or current
        if not current:
            raise ValueError(f"anchor {part!r} names no file in {answered_by!r}")
        start = int(match["start"])
        end = int(match["end"] or start)
        if end < start:
            raise ValueError(f"backwards anchor range {part!r} in {answered_by!r}")
        anchors.append((current, start, end))
    return anchors


def test_the_committed_case_set_is_valid_and_pinned(eval_dir: Path) -> None:
    case_set = load_case_set(eval_dir / "cases.json")
    assert case_set.schema == "indexed.eval.cases.v1"
    assert len(case_set.cases) == 15
    assert len(set(case_set.ids)) == 15
    answerable = [case for case in case_set.cases if case.answerable]
    assert len(answerable) == 11
    assert len(case_set.cases) - len(answerable) == 4
    for case in case_set.cases:
        assert case.provenance, case.id
        assert case.rationale, case.id
        if case.answerable:
            assert case.answered_by, case.id
    assert len(case_set.sha256) == 64


def test_every_judged_document_exists_in_the_pinned_corpus(eval_dir: Path) -> None:
    corpus_names = {path.name for path in (eval_dir / "corpus").iterdir()}
    case_set = load_case_set(eval_dir / "cases.json")
    for case in case_set.cases:
        for doc in [*case.relevant, *case.distractors]:
            assert doc in corpus_names, f"{case.id}: {doc} not in the pinned corpus"


def test_every_answered_by_anchor_resolves_in_the_pinned_corpus(eval_dir: Path) -> None:
    """An anchor that points at a blank line justifies nothing.

    ``answered_by`` is the evidence behind each judgement, so it is resolved, not
    just required to be non-empty: the file must be a judged-relevant document,
    the line must exist, and both ends of a range must land on prose. Line
    numbers in a pinned copy cannot move (the corpus is byte-frozen), so a failure
    here means the anchor was transcribed from a different revision.
    """
    case_set = load_case_set(eval_dir / "cases.json")
    corpus = eval_dir / "corpus"
    for case in case_set.cases:
        if not case.answerable:
            assert not case.answered_by, f"{case.id}: unanswerable cases cite no anchor"
            continue
        anchors = _anchors(case.answered_by)
        assert anchors, f"{case.id}: an answerable case needs an anchor"
        assert {name for name, _, _ in anchors} <= set(case.relevant), (
            f"{case.id}: {case.answered_by} cites a document the case does not "
            f"judge relevant ({case.relevant})"
        )
        for name, start, end in anchors:
            path = corpus / name
            assert path.is_file(), f"{case.id}: {name} is not in the pinned corpus"
            lines = path.read_text(encoding="utf-8").splitlines()
            assert 1 <= start <= end <= len(lines), (
                f"{case.id}: {name}:{start}-{end} is outside 1-{len(lines)}"
            )
            for number in {start, end}:
                assert lines[number - 1].strip(), (
                    f"{case.id}: {name}:{number} is blank — the anchor drifted"
                )


def test_a_bare_anchor_line_inherits_the_previous_file() -> None:
    assert _anchors("lessons.md:366, 400, 800, 1071-1073") == [
        ("lessons.md", 366, 366),
        ("lessons.md", 400, 400),
        ("lessons.md", 800, 800),
        ("lessons.md", 1071, 1073),
    ]
    assert _anchors("tech.md:391, tech-app.md:169-180") == [
        ("tech.md", 391, 391),
        ("tech-app.md", 169, 180),
    ]


@pytest.mark.parametrize(
    "answered_by",
    ["12", "lessons.md:", "lessons.md:1071-1070", "lessons.md:1071; 1073"],
)
def test_an_unparseable_anchor_is_refused(answered_by: str) -> None:
    with pytest.raises(ValueError, match="anchor"):
        _anchors(answered_by)


def test_missing_case_file_is_an_eval_data_error(tmp_path: Path) -> None:
    with pytest.raises(EvalDataError, match="not found"):
        load_case_set(tmp_path / "absent.json")


def test_wrong_schema_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "cases.json", _case_set([_minimal_case()], schema="other"))
    with pytest.raises(EvalDataError, match="expected schema"):
        load_case_set(path)


def test_empty_case_set_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "cases.json", _case_set([]))
    with pytest.raises(EvalDataError, match="empty"):
        load_case_set(path)


def test_missing_provenance_is_refused(tmp_path: Path) -> None:
    case = _minimal_case(id="no-prov")
    case.pop("provenance")
    path = _write(tmp_path / "cases.json", _case_set([case]))
    with pytest.raises(EvalDataError, match="provenance"):
        load_case_set(path)


def test_missing_rationale_is_refused(tmp_path: Path) -> None:
    case = _minimal_case(id="no-rationale")
    case.pop("rationale")
    path = _write(tmp_path / "cases.json", _case_set([case]))
    with pytest.raises(EvalDataError, match="rationale"):
        load_case_set(path)


def test_duplicate_case_ids_are_refused(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "cases.json",
        _case_set([_minimal_case(), _minimal_case()]),
    )
    with pytest.raises(EvalDataError, match="duplicate id"):
        load_case_set(path)


def test_a_document_cannot_be_both_relevant_and_a_distractor(tmp_path: Path) -> None:
    case = _minimal_case(relevant=["plan.md"], distractors=["plan.md"])
    path = _write(tmp_path / "cases.json", _case_set([case]))
    with pytest.raises(EvalDataError, match="both relevant"):
        load_case_set(path)


def test_corpus_revision_reports_the_pinned_tree(eval_dir: Path) -> None:
    revision = corpus_revision(eval_dir / "corpus", eval_dir / "corpus.json")
    assert revision["corpus_id"] == "indexed-docs"
    assert len(revision["files"]) == 11
    assert len(revision["tree_sha256"]) == 64
    assert all(len(entry["sha256"]) == 64 for entry in revision["files"])


def test_corpus_drift_is_refused_unless_explicitly_allowed(
    tmp_path: Path, eval_dir: Path
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for source in (eval_dir / "corpus").iterdir():
        (corpus / source.name).write_bytes(source.read_bytes())
    (corpus / "plan.md").write_text("edited after pinning", encoding="utf-8")

    manifest = eval_dir / "corpus.json"
    with pytest.raises(EvalDataError, match="drift"):
        corpus_revision(corpus, manifest)
    # --allow-corpus-drift measures anyway, reporting the bytes it actually read.
    revision = corpus_revision(corpus, manifest, verify=False)
    assert revision["tree_sha256"] != json.loads(manifest.read_text())["tree_sha256"]


def test_missing_corpus_file_is_refused(tmp_path: Path, eval_dir: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for source in (eval_dir / "corpus").iterdir():
        if source.name == "lessons.md":
            continue
        (corpus / source.name).write_bytes(source.read_bytes())
    with pytest.raises(EvalDataError, match="missing"):
        corpus_revision(corpus, eval_dir / "corpus.json")


def test_write_json_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "report.json"
    write_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert target.read_text(encoding="utf-8").endswith("\n")
