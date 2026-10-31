"""Pin runtime settings without persisting or leaking singleton overrides."""

import pytest

from indexed.config import get_config
from indexed.eval.runner import RunConfig, _model_cache_hint, run_eval
from tests.unit.indexed.eval.test_runner import _mini_cases

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path,value",
    [
        ("sources.files.path", "/missing/eval-unrelated-path"),
        ("mcp.port", -1),
        ("core.v1.indexing.chunk_size", 0),
        ("core.engine", "invalid"),
    ],
)
def test_v2_eval_ignores_invalid_unrelated_config_and_restores_it(path, value):
    from indexed.eval.runtime_config import evaluation_config
    from indexed.core.v2.config_models import CoreV2EmbeddingConfig

    service = get_config()
    service.set_overlay(path, value)
    before = service.load_raw()
    with evaluation_config(RunConfig()) as effective:
        assert effective["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert service.bind().get(CoreV2EmbeddingConfig).batch_size == 32
    assert service.load_raw() == before


def test_isolated_eval_still_refuses_invalid_own_settings():
    from indexed.config.errors import ConfigValidationError
    from indexed.eval.runtime_config import evaluation_config

    service = get_config()
    before = service.load_raw()
    with pytest.raises(ConfigValidationError, match="core.v2.embedding"):
        with evaluation_config(RunConfig(embedding_batch_size=0)):
            pytest.fail("invalid eval settings reached execution")
    assert service.load_raw() == before


@pytest.mark.parametrize("fail", [False, True])
def test_eval_pins_config_and_restores_existing_overlay(
    tmp_path, eval_dir, monkeypatch, fail
):
    """Prevent ambient settings and failed builds from leaking singleton overrides."""
    service = get_config()
    service.set_overlay("core.v2.embedding.model_name", "ambient-model")
    service.set_overlay("core.v2.rerank.top_n", 99)
    service.set_overlay("custom.keep", {"value": [1]})
    before = service.load_raw()
    cases = _mini_cases(tmp_path / "cases.json", eval_dir / "corpus", query="q")

    def build(*args, **kwargs):
        """Inspect effective settings during collection work and optionally fail restoration."""
        from indexed.core.v2.config_models import (
            CoreV2EmbeddingConfig,
            CoreV2RerankConfig,
            CoreV2SearchConfig,
        )

        provider = service.bind()
        assert (
            provider.get(CoreV2EmbeddingConfig).model_name
            == "sentence-transformers/all-MiniLM-L6-v2"
        )
        assert provider.get(CoreV2EmbeddingConfig).batch_size == 32
        assert provider.get(CoreV2SearchConfig).score_threshold == 0.0
        assert (
            provider.get(CoreV2RerankConfig).model
            == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        assert provider.get(CoreV2RerankConfig).top_n == 10
        assert provider.get(CoreV2RerankConfig).enabled is True
        service.set_overlay("custom.keep", {"value": [2]})
        if fail:
            raise RuntimeError("build failed")

    monkeypatch.setattr("indexed.eval.runner.build_collection", build)
    monkeypatch.setattr(
        "indexed.eval.runner._search_one",
        lambda *args: {"eval-corpus": {"results": [], "scoreKind": "rerank"}},
    )
    monkeypatch.setattr(service, "save_raw", lambda *args: pytest.fail("disk write"))
    kwargs = dict(
        cases_path=cases,
        corpus_dir=eval_dir / "corpus",
        corpus_manifest=eval_dir / "corpus.json",
        config=RunConfig(rerank=True),
    )
    if fail:
        with pytest.raises(RuntimeError, match="build failed"):
            run_eval(**kwargs)
    else:
        report = run_eval(**kwargs)
        assert (
            report["config"]["embedding_model"]
            == "sentence-transformers/all-MiniLM-L6-v2"
        )
        assert report["config"]["embedding_batch_size"] == 32
        assert report["config"]["score_threshold"] == 0.0
        assert (
            report["config"]["reranker_model"] == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        assert report["config"]["reranker_top_n"] == 10
        assert "reranker_model_cache" in report["environment"]
    assert service.load_raw() == before


def test_temporary_overlay_restores_nested_scopes_without_disk(tmp_path):
    service = get_config()
    service.set_overlay("core.engine", "1")
    before = service.load_raw()
    with service.temporary_overlay({"core.engine": "2"}):
        assert service.get("core.engine") == "2"
        with pytest.raises(ValueError), service.temporary_overlay({"core.engine": "1"}):
            assert service.get("core.engine") == "1"
            raise ValueError("abort")
        assert service.get("core.engine") == "2"
    assert service.load_raw() == before


@pytest.mark.parametrize(
    "setting,value",
    [
        ("embedding_model", "other/model"),
        ("embedding_batch_size", 16),
        ("score_threshold", 0.5),
        ("reranker_model", "other/reranker"),
        ("reranker_top_n", 3),
    ],
)
def test_effective_setting_changes_prevent_comparison(
    tmp_path, eval_dir, monkeypatch, setting, value
):
    from indexed.eval.compare import compare_reports

    cases = _mini_cases(tmp_path / "cases.json", eval_dir / "corpus", query="q")
    monkeypatch.setattr("indexed.eval.runner.build_collection", lambda *a, **kw: None)
    monkeypatch.setattr(
        "indexed.eval.runner._search_one",
        lambda *a: {"eval-corpus": {"results": [], "scoreKind": "rerank"}},
    )
    kwargs = dict(
        cases_path=cases,
        corpus_dir=eval_dir / "corpus",
        corpus_manifest=eval_dir / "corpus.json",
    )
    original = run_eval(**kwargs, config=RunConfig(rerank=True))
    candidate = run_eval(**kwargs, config=RunConfig(rerank=True, **{setting: value}))
    assert candidate["config"][setting] == value
    assert compare_reports(original, candidate)["verdict"] == "incomparable"


def test_dense_report_omits_inactive_reranker_evidence(tmp_path, eval_dir, monkeypatch):
    cases = _mini_cases(tmp_path / "cases.json", eval_dir / "corpus", query="q")
    monkeypatch.setattr("indexed.eval.runner.build_collection", lambda *a, **kw: None)
    monkeypatch.setattr(
        "indexed.eval.runner._search_one",
        lambda *a: {"eval-corpus": {"results": [], "scoreKind": "cosine"}},
    )
    report = run_eval(
        cases_path=cases,
        corpus_dir=eval_dir / "corpus",
        corpus_manifest=eval_dir / "corpus.json",
    )
    assert report["config"]["reranker_model"] is None
    assert report["config"]["reranker_top_n"] is None
    assert "reranker_model_cache" not in report["environment"]


def test_cache_evidence_names_only_selected_snapshot_weights(tmp_path, monkeypatch):
    """Prevent stale snapshots from supplying weights evidence for the active revision."""
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    root = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
    for revision, filename in [
        ("old", "pytorch_model.bin"),
        ("active", "model.safetensors"),
    ]:
        folder = root / "snapshots" / revision
        folder.mkdir(parents=True)
        (folder / filename).write_bytes(b"weights")
        (folder / "config.json").write_text("{}")
    (root / "refs").mkdir()
    (root / "refs" / "main").write_text("active")
    hint = _model_cache_hint("sentence-transformers/all-MiniLM-L6-v2")
    assert hint["selected_snapshot"] == "active"
    assert hint["snapshot_path"] == str(root / "snapshots" / "active")
    assert hint["weights"] == ["model.safetensors"]
    (root / "refs" / "main").write_text("missing")
    assert (
        _model_cache_hint("sentence-transformers/all-MiniLM-L6-v2")["present"] is False
    )


@pytest.mark.parametrize("has_reference", [False, True])
def test_repo_model_cache_evidence_requires_resolvable_config(
    tmp_path, monkeypatch, has_reference
):
    """Match Hub cache lookup when weights alone cannot resolve a model configuration."""
    from huggingface_hub import try_to_load_from_cache

    model = "sentence-transformers/all-MiniLM-L6-v2"
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    root = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
    snapshot = root / "snapshots" / "orphan"
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").write_bytes(b"weights")
    if has_reference:
        (root / "refs").mkdir()
        (root / "refs" / "main").write_text("orphan")
    else:
        (snapshot / "config.json").write_text("{}")
    assert try_to_load_from_cache(model, "config.json", cache_dir=str(tmp_path)) is None
    evidence = _model_cache_hint(model)
    assert evidence["present"] is False
    assert evidence["selected_snapshot"] is None
    assert evidence["snapshot_path"] is None
    assert evidence["weights"] == []


def test_measured_source_fingerprint_tracks_code_and_lock_but_not_reports(tmp_path):
    from indexed.eval.runtime_config import source_fingerprint

    source = tmp_path / "src" / "indexed" / "core"
    source.mkdir(parents=True)
    (source / "engine.py").write_text("retrieval = 1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n")
    lock = tmp_path / "uv.lock"
    lock.write_text("version = 1\n")
    first = source_fingerprint(tmp_path)
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "baseline.json").write_text("{}")
    assert source_fingerprint(tmp_path) == first
    lock.write_text("version = 2\n")
    assert source_fingerprint(tmp_path) != first
    lock.write_text("version = 1\n")
    (source / "engine.py").write_text("retrieval = 2\n")
    assert source_fingerprint(tmp_path) != first


def test_v1_cache_evidence_retains_direct_snapshot_loader_fallback(
    tmp_path, monkeypatch
):
    from indexed.core.v1.engine.indexes.embeddings.model_manager import (
        _resolve_snapshot_path,
    )

    model = "sentence-transformers/all-MiniLM-L6-v2"
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    snapshot = (
        tmp_path
        / "models--sentence-transformers--all-MiniLM-L6-v2"
        / "snapshots"
        / "orphan"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").write_bytes(b"weights")
    assert _resolve_snapshot_path(model) == str(snapshot)
    evidence = _model_cache_hint(model, engine="1")
    assert evidence["selected_snapshot"] == "orphan"
    assert evidence["present"] is True


def test_v1_report_records_model_instead_of_indexer_and_disabled_l2_threshold(
    tmp_path, eval_dir, monkeypatch
):
    cases = _mini_cases(tmp_path / "cases.json", eval_dir / "corpus", query="q")
    monkeypatch.setattr("indexed.eval.runner.build_collection", lambda *a, **kw: None)
    monkeypatch.setattr(
        "indexed.eval.runner._search_one",
        lambda *a: {
            "eval-corpus": {
                "results": [],
                "indexerName": "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
            }
        },
    )
    report = run_eval(
        cases_path=cases,
        corpus_dir=eval_dir / "corpus",
        corpus_manifest=eval_dir / "corpus.json",
        config=RunConfig(engine="1"),
    )
    assert (
        report["config"]["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    )
    assert report["config"]["score_threshold"] is None


def test_v1_rejects_model_knob_that_its_fixed_source_indexer_cannot_apply():
    with pytest.raises(ValueError, match="engine '1'.*embedding model"):
        RunConfig(engine="1", embedding_model="other/model")


def test_environment_records_source_and_numerical_dependency_evidence():
    from indexed.eval.runner import _environment

    environment = _environment()
    assert len(environment["indexed_git_rev"]) == 40
    assert type(environment["indexed_worktree_dirty"]) is bool
    assert len(environment["indexed_source_sha256"]) == 64
    assert set(environment["numerical_dependencies"]) == {
        "numpy",
        "torch",
        "transformers",
        "sentence-transformers",
        "llama-index-core",
    }
    assert all(environment["numerical_dependencies"].values())
