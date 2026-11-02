"""Evaluator-only path context and common launcher regressions."""

from copy import deepcopy
from pathlib import Path
import importlib.util
import pytest

pytestmark = pytest.mark.unit


def document(root):
    physical = str(root / "sample.py")
    return dict(
        fileFullPath=physical,
        fileRelativePath="sample.py",
        modifiedTime="today",
        content=[
            dict(
                text=f"# {physical}\nbody mentions {physical}",
                metadata=dict(file_path=physical),
            ),
            dict(text=f"{physical}\nplain body", metadata=dict(file_path=physical)),
            dict(text=f"# authored heading\n{physical}", metadata={}),
        ],
    )


def test_canonical_conversion_preserves_body_metadata_and_product_connector(tmp_path):
    from indexed.eval.canonical import CanonicalConverter
    from indexed.connectors.files.files_document_converter import FilesDocumentConverter

    raw = document(tmp_path)
    original = deepcopy(raw)
    ordinary = FilesDocumentConverter()
    converter = CanonicalConverter(ordinary)
    result = converter.convert(raw)[0]
    assert (
        result["chunks"][1]["indexedData"]
        == f"# eval/corpus/sample.py\nbody mentions {raw['fileFullPath']}"
    )
    assert result["chunks"][2]["indexedData"] == "eval/corpus/sample.py\nplain body"
    assert result["chunks"][3]["indexedData"] == raw["content"][2]["text"]
    assert result["url"] == f"file://{raw['fileFullPath']}"
    assert result["chunks"][1]["metadata"] == raw["content"][0]["metadata"]
    assert raw == original
    assert raw["fileFullPath"] in ordinary.convert(raw)[0]["chunks"][1]["indexedData"]


def test_distinct_roots_have_equal_canonical_text_and_input_digests(tmp_path):
    from indexed.eval.canonical import CanonicalConverter
    from indexed.connectors.files.files_document_converter import FilesDocumentConverter

    results, evidence = [], []
    for root in [tmp_path / "a", tmp_path / "long-root!"]:
        raw = document(root)
        raw["content"] = [
            dict(
                text=f"# {raw['fileFullPath']}\nconstant body",
                metadata=dict(file_path=raw["fileFullPath"]),
            )
        ]
        converter = CanonicalConverter(FilesDocumentConverter())
        results.append(converter.convert(raw)[0]["chunks"])
        evidence.append(converter.evidence())
    assert [c["indexedData"] for c in results[0]] == [
        c["indexedData"] for c in results[1]
    ]
    assert evidence[0] == evidence[1]
    assert evidence[0]["boundary"] == "normalized-converter-chunks"


def test_common_launcher_does_not_replace_side_modules():
    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "common_eval", root / "scripts/eval_ab_run.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence = module.side_provenance(root)
    assert all(
        Path(origin).is_relative_to(root)
        for origin in evidence["import_origins"].values()
    )
    assert evidence["lock_sha256"]
    assert evidence["engine_revision"]


def test_common_launcher_injects_legacy_runner_without_modifying_it(
    monkeypatch, tmp_path
):
    import inspect
    import subprocess
    import indexed.eval.runner as current_runner

    root = Path(__file__).resolve().parents[4]
    # Execute the actual captured pre-normalization runner with its existing seam.
    source = subprocess.check_output(
        [
            "git",
            "show",
            "6f98736bd1ac521598c73fe8aeaf61086a8020e6:src/indexed/eval/runner.py",
        ],
        cwd=root,
        text=True,
    )
    legacy_file = tmp_path / "legacy_runner.py"
    legacy_file.write_text(source)
    import sys

    spec = importlib.util.spec_from_file_location("legacy_runner", legacy_file)
    assert spec is not None and spec.loader is not None
    legacy = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "legacy_runner", legacy)
    spec.loader.exec_module(legacy)
    assert "connector_factory" in inspect.signature(legacy.run_eval).parameters
    assert "input_context_policy" not in source
    received = []

    def build(corpus_dir, collections_path, config, *, connector_factory=None):
        received.append(connector_factory)

    monkeypatch.setattr(legacy, "build_collection", build)
    monkeypatch.setattr(
        legacy,
        "_search_one",
        lambda query, collections_path, config: {
            config.collection: {
                "results": [],
                "scoreKind": "cosine",
                "indexerName": "model",
            }
        },
    )
    spec = importlib.util.spec_from_file_location(
        "common_eval", root / "scripts/eval_ab_run.py"
    )
    assert spec is not None and spec.loader is not None
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    monkeypatch.setattr(current_runner, "run_eval", legacy.run_eval)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    report = common.measure(root, revision, revision)
    assert received and received[0].policy == "eval-corpus-relative-v1"
    assert report["config"]["input_context_policy"] == "eval-corpus-relative-v1"
    assert report["environment"]["common_harness"]["files_sha256"]["canonical_helper"]
    assert report["environment"]["common_harness"]["content_matches_revision"] is False


def test_default_factory_uses_real_side_reader_under_distinct_roots(tmp_path):
    from indexed.eval.runner import _files_connector_factory

    evidence = []
    for directory in (tmp_path / "a", tmp_path / "long-root!"):
        directory.mkdir()
        (directory / "sample.py").write_text("def answer():\n    return 42\n")
        (directory / "note.txt").write_text("An ordinary plaintext note.")
        factory = _files_connector_factory(directory)
        connector = factory(None)
        docs = list(connector.reader.read_all_documents())
        assert len(docs) == 2
        converted = [
            result for doc in docs for result in connector.converter.convert(doc)
        ]
        assert all(
            str(directory) not in chunk["indexedData"]
            for doc in converted
            for chunk in doc["chunks"]
        )
        assert any(
            "eval/corpus/sample.py" in chunk["indexedData"]
            for doc in converted
            for chunk in doc["chunks"]
        )
        assert all(doc["url"].startswith(f"file://{directory}") for doc in converted)
        evidence.append(factory.evidence())
    assert evidence[0] == evidence[1]


def test_common_launcher_rejects_another_side_imports(tmp_path):
    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "common_eval", root / "scripts/eval_ab_run.py"
    )
    assert spec is not None and spec.loader is not None
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    with pytest.raises(ValueError, match="outside measured side"):
        common.side_provenance(tmp_path)


def test_explicit_custom_factory_remains_usable(monkeypatch):
    from indexed.eval.runner import run_eval

    factory = object()
    received = []

    def build(corpus_dir, collections_path, config, *, connector_factory=None):
        received.append(connector_factory)

    monkeypatch.setattr("indexed.eval.runner.build_collection", build)
    monkeypatch.setattr(
        "indexed.eval.runner._search_one",
        lambda query, collections_path, config: {
            config.collection: {
                "results": [],
                "scoreKind": "cosine",
                "indexerName": "model",
            }
        },
    )
    report = run_eval(connector_factory=factory)
    assert received == [factory]
    assert report["config"]["input_context_policy"] == "custom"
    assert "converter_inputs" not in report["environment"]


def test_launcher_output_refuses_symlink_without_changing_victim(monkeypatch, tmp_path):
    import sys

    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "common_eval", root / "scripts/eval_ab_run.py"
    )
    assert spec is not None and spec.loader is not None
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    victim = tmp_path / "victim.json"
    victim.write_text("keep this content")
    output = tmp_path / "report.json"
    output.symlink_to(victim)
    monkeypatch.setattr(common, "measure", lambda *args: {"measured": True})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_ab_run",
            "--root",
            str(root),
            "--out",
            str(output),
            "--harness-revision",
            "a" * 40,
            "--engine-revision",
            "a" * 40,
        ],
    )
    with pytest.raises(ValueError, match="regular"):
        common.main()
    assert victim.read_text() == "keep this content"
    assert output.is_symlink()


def test_launcher_output_overwrites_regular_file_with_identical_json(
    monkeypatch, tmp_path
):
    import json
    import sys

    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "common_eval", root / "scripts/eval_ab_run.py"
    )
    assert spec is not None and spec.loader is not None
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    report = {"measured": True, "values": [1, "context"]}
    output = tmp_path / "report.json"
    output.write_text("old report")
    monkeypatch.setattr(common, "measure", lambda *args: report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_ab_run",
            "--root",
            str(root),
            "--out",
            str(output),
            "--harness-revision",
            "a" * 40,
            "--engine-revision",
            "a" * 40,
        ],
    )
    common.main()
    assert (
        output.read_bytes()
        == (json.dumps(report, allow_nan=False, indent=2) + "\n").encode()
    )
    assert list(tmp_path.iterdir()) == [output]


def test_launcher_output_rejects_directory_and_cleans_failed_temporary(
    monkeypatch, tmp_path
):
    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "common_eval", root / "scripts/eval_ab_run.py"
    )
    assert spec is not None and spec.loader is not None
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular"):
        common.write_report(directory, {})
    output = tmp_path / "report.json"
    output.write_text("old report")

    def fail_replace(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(common.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        common.write_report(output, {"new": True})
    assert output.read_text() == "old report"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "directory",
        "report.json",
    ]
