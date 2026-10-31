"""Pinned case-set + corpus-manifest loading and drift refusal (issue #204)."""

from __future__ import annotations

import json
import hashlib
import shutil
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
    payload = {
        "schema": "indexed.eval.cases.v1",
        "corpus_id": "indexed-docs",
        "cases": cases,
    }
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


@pytest.mark.integration
def test_the_committed_case_set_is_valid_and_pinned(eval_dir: Path) -> None:
    """Guard the reviewed case balance and required judgment evidence against drift."""
    case_set = load_case_set(eval_dir / "cases.json")
    assert case_set.schema == "indexed.eval.cases.v1"
    assert len(case_set.cases) == 23
    assert len(set(case_set.ids)) == 23
    answerable = [case for case in case_set.cases if case.answerable]
    assert len(answerable) == 19
    assert len(case_set.cases) - len(answerable) == 4
    for case in case_set.cases:
        assert case.provenance, case.id
        assert case.rationale, case.id
        if case.answerable:
            assert case.answered_by, case.id
    assert len(case_set.sha256) == 64


@pytest.mark.integration
def test_every_judged_document_exists_in_the_pinned_corpus(eval_dir: Path) -> None:
    """Prevent judgments from referring to documents outside the measured corpus."""
    corpus_names = {path.name for path in (eval_dir / "corpus").iterdir()}
    case_set = load_case_set(eval_dir / "cases.json")
    for case in case_set.cases:
        for doc in [*case.relevant, *case.distractors]:
            assert doc in corpus_names, f"{case.id}: {doc} not in the pinned corpus"


@pytest.mark.integration
def test_every_answered_by_anchor_resolves_in_the_pinned_corpus(eval_dir: Path) -> None:
    """An anchor that points at a blank line justifies nothing.

    ``answered_by`` is the evidence behind each judgement, so it is resolved, not
    just required to be non-empty: the file must be a judged-relevant document,
    the line must exist, and both ends of a range must be nonblank. Semantic relevance still needs manual review. Line
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


@pytest.mark.unit
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


@pytest.mark.unit
@pytest.mark.parametrize(
    "answered_by",
    ["12", "lessons.md:", "lessons.md:1071-1070", "lessons.md:1071; 1073"],
)
def test_an_unparseable_anchor_is_refused(answered_by: str) -> None:
    with pytest.raises(ValueError, match="anchor"):
        _anchors(answered_by)


@pytest.mark.unit
def test_missing_case_file_is_an_eval_data_error(tmp_path: Path) -> None:
    with pytest.raises(EvalDataError, match="not found"):
        load_case_set(tmp_path / "absent.json")


@pytest.mark.unit
def test_wrong_schema_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "cases.json", _case_set([_minimal_case()], schema="other"))
    with pytest.raises(EvalDataError, match="expected schema"):
        load_case_set(path)


@pytest.mark.unit
def test_empty_case_set_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "cases.json", _case_set([]))
    with pytest.raises(EvalDataError, match="empty"):
        load_case_set(path)


@pytest.mark.unit
def test_missing_provenance_is_refused(tmp_path: Path) -> None:
    case = _minimal_case(id="no-prov")
    case.pop("provenance")
    path = _write(tmp_path / "cases.json", _case_set([case]))
    with pytest.raises(EvalDataError, match="provenance"):
        load_case_set(path)


@pytest.mark.unit
def test_missing_rationale_is_refused(tmp_path: Path) -> None:
    case = _minimal_case(id="no-rationale")
    case.pop("rationale")
    path = _write(tmp_path / "cases.json", _case_set([case]))
    with pytest.raises(EvalDataError, match="rationale"):
        load_case_set(path)


@pytest.mark.unit
def test_duplicate_case_ids_are_refused(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "cases.json",
        _case_set([_minimal_case(), _minimal_case()]),
    )
    with pytest.raises(EvalDataError, match="duplicate id"):
        load_case_set(path)


@pytest.mark.unit
def test_a_document_cannot_be_both_relevant_and_a_distractor(tmp_path: Path) -> None:
    case = _minimal_case(relevant=["plan.md"], distractors=["plan.md"])
    path = _write(tmp_path / "cases.json", _case_set([case]))
    with pytest.raises(EvalDataError, match="both relevant"):
        load_case_set(path)


@pytest.mark.integration
def test_corpus_revision_reports_the_pinned_tree(eval_dir: Path) -> None:
    """Require corpus provenance to retain complete file and tree hash evidence."""
    revision = corpus_revision(eval_dir / "corpus", eval_dir / "corpus.json")
    assert revision["corpus_id"] == "indexed-docs"
    assert len(revision["files"]) == 16
    assert len(revision["tree_sha256"]) == 64
    assert all(len(entry["sha256"]) == 64 for entry in revision["files"])


@pytest.mark.integration
def test_corpus_drift_is_refused_unless_explicitly_allowed(
    tmp_path: Path, eval_dir: Path
) -> None:
    """Ensure bypassed drift records the actual bytes instead of the old tree hash."""
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


@pytest.mark.integration
def test_missing_corpus_file_is_refused(tmp_path: Path, eval_dir: Path) -> None:
    """Prevent partial corpus copies from masquerading as the pinned experiment."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for source in (eval_dir / "corpus").iterdir():
        if source.name == "lessons.md":
            continue
        (corpus / source.name).write_bytes(source.read_bytes())
    with pytest.raises(EvalDataError, match="missing"):
        corpus_revision(corpus, eval_dir / "corpus.json")


@pytest.mark.unit
def test_write_json_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "report.json"
    write_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert target.read_text(encoding="utf-8").endswith("\n")


@pytest.mark.unit
@pytest.mark.parametrize("text", ["{", "[]", "null", '"text"'])
@pytest.mark.parametrize("artifact", ["cases", "corpus"])
def test_malformed_artifact_is_a_data_error(tmp_path, text, artifact):
    """Keep both artifact loaders on their typed diagnostic path for invalid JSON."""
    path = tmp_path / "artifact.json"
    path.write_text(text)
    with pytest.raises(EvalDataError, match=str(path)):
        if artifact == "cases":
            load_case_set(path)
        else:
            corpus_revision(tmp_path, path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [
        ("cases", {}),
        ("cases", "case"),
        ("cases", [None]),
        ("corpus_id", None),
        ("corpus_id", ""),
        ("description", []),
    ],
)
def test_case_set_rejects_wrong_field_shapes(tmp_path, field, value):
    payload = _case_set([_minimal_case()])
    payload[field] = value
    with pytest.raises(EvalDataError, match=field):
        load_case_set(_write(tmp_path / "cases.json", payload))


@pytest.mark.unit
@pytest.mark.parametrize("field", ["relevant", "distractors"])
@pytest.mark.parametrize("value", [None, False, 0, "", {}, "plan.md"])
def test_falsey_non_lists_are_not_empty_judgments(tmp_path, field, value):
    case = _minimal_case(**{field: value})
    with pytest.raises(EvalDataError, match=field):
        load_case_set(_write(tmp_path / "cases.json", _case_set([case])))


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"id": " "},
        {"id": None},
        {"answered_by": []},
        {"relevant": ["../plan.md"]},
        {"relevant": [" plan.md"]},
        {"relevant": ["plan.md", "Plan.MD"]},
        {"relevant": ["Plan.MD"], "distractors": ["plan.md"]},
    ],
)
def test_ambiguous_case_identity_is_refused(tmp_path, overrides):
    with pytest.raises(EvalDataError):
        load_case_set(
            _write(tmp_path / "cases.json", _case_set([_minimal_case(**overrides)]))
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "field,value",
    [
        ("files", None),
        ("files", {}),
        ("files", [None]),
        ("files", [{}]),
        ("corpus_id", None),
        ("source_repo_rev", []),
        ("tree_sha256", "broken"),
    ],
)
def test_manifest_rejects_wrong_field_shapes(tmp_path, eval_dir, field, value):
    payload = json.loads((eval_dir / "corpus.json").read_text())
    payload[field] = value
    manifest = _write(tmp_path / "corpus.json", payload)
    with pytest.raises(EvalDataError, match="corpus.json"):
        corpus_revision(eval_dir / "corpus", manifest)


@pytest.mark.integration
@pytest.mark.parametrize(
    "field,value",
    [
        ("path", "../README.md"),
        ("path", "/README.md"),
        ("path", "nested/README.md"),
        ("path", "nested\\README.md"),
        ("path", None),
        ("sha256", "bad"),
        ("bytes", False),
        ("source", []),
    ],
)
def test_manifest_file_fields_are_validated(tmp_path, eval_dir, field, value):
    payload = json.loads((eval_dir / "corpus.json").read_text())
    payload["files"][0][field] = value
    with pytest.raises(EvalDataError, match="corpus.json"):
        corpus_revision(eval_dir / "corpus", _write(tmp_path / "corpus.json", payload))


@pytest.mark.integration
@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "case_collision", "nested", "symlink", "directory", "tree", "bytes"],
)
def test_corpus_identity_and_full_pinning_are_enforced(tmp_path, eval_dir, mutation):
    """Reject ambiguous identities and filesystem substitutions even with a manifest."""
    corpus = tmp_path / "corpus"
    shutil.copytree(eval_dir / "corpus", corpus)
    payload = json.loads((eval_dir / "corpus.json").read_text())
    if mutation in {"duplicate", "case_collision"}:
        entry = dict(payload["files"][0])
        if mutation == "case_collision":
            entry["path"] = entry["path"].lower()
            (corpus / entry["path"]).write_bytes((corpus / "README.md").read_bytes())
        payload["files"].append(entry)
    elif mutation == "nested":
        (corpus / "nested").mkdir()
        (corpus / "nested" / "extra.md").write_text("untracked")
    elif mutation in {"symlink", "directory"}:
        original = corpus / "README.md"
        content = original.read_bytes()
        original.unlink()
        if mutation == "directory":
            original.mkdir()
        else:
            target = tmp_path / "outside.md"
            target.write_bytes(content)
            original.symlink_to(target)
    else:
        if mutation == "tree":
            payload["tree_sha256"] = hashlib.sha256(b"wrong").hexdigest()
        else:
            payload["files"][0]["bytes"] += 1
    with pytest.raises(EvalDataError):
        corpus_revision(corpus, _write(tmp_path / "corpus.json", payload))


@pytest.mark.unit
@pytest.mark.parametrize("name", ["file:plan.md", "File:plan.md", "other:plan.md"])
@pytest.mark.parametrize("artifact", ["cases", "corpus"])
def test_colon_names_cannot_enter_the_judged_corpus(tmp_path, name, artifact):
    """Keep document identities unambiguous under the file-and-line anchor syntax."""
    if artifact == "cases":
        path = _write(
            tmp_path / "cases.json", _case_set([_minimal_case(relevant=[name])])
        )
        with pytest.raises(EvalDataError, match="flat document path"):
            load_case_set(path)
    else:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        content = b"the relevant document"
        (corpus / name).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        manifest = _write(
            tmp_path / "corpus.json",
            {
                "schema": "indexed.eval.corpus.v1",
                "corpus_id": "indexed-docs",
                "source_repo_rev": "test",
                "tree_sha256": hashlib.sha256(
                    f"{digest}  {name}\n".encode()
                ).hexdigest(),
                "files": [
                    {
                        "path": name,
                        "source": "plan.md",
                        "sha256": digest,
                        "bytes": len(content),
                    }
                ],
            },
        )
        with pytest.raises(EvalDataError, match="flat document path"):
            corpus_revision(corpus, manifest)
