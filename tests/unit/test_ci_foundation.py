import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())


def test_benchmark_caps_match_in_both_jobs():
    jobs = _workflow("python-benchmark.yml")["jobs"]
    maps = []
    for job in ("benchmark", "refresh-baseline"):
        step = next(
            s for s in jobs[job]["steps"] if "threshold-map" in s.get("with", {})
        )
        maps.append(step["with"]["threshold-map"])
    assert maps[0] == maps[1]
    maps = [json.loads(value) for value in maps]
    assert maps[0]["batch_parse"] == 12
    assert maps[0]["full_connector_pipeline"] == 20
    assert maps[0]["full_connector_pipeline_mixed"] == 30
    assert list(maps[0]).index("full_connector_pipeline_mixed") < list(maps[0]).index(
        "full_connector_pipeline"
    )


def test_system_suite_ensures_model_before_pytest():
    steps = _workflow("python-ci.yml")["jobs"]["build-and-system-tests"]["steps"]
    ensure = next(
        i
        for i, step in enumerate(steps)
        if "ensure_model('all-MiniLM-L6-v2')" in step.get("run", "")
    )
    suite = next(
        i
        for i, step in enumerate(steps)
        if "pytest tests/system/" in step.get("run", "")
    )
    assert ensure < suite


@pytest.mark.parametrize("selection", ["hub", "home", "default"])
def test_model_cache_step_survives_isolated_home(tmp_path, selection):
    steps = _workflow("python-ci.yml")["jobs"]["build-and-system-tests"]["steps"]
    cache = next(i for i, s in enumerate(steps) if s.get("name") == "Pin model cache")
    ensure = next(
        i
        for i, s in enumerate(steps)
        if s.get("name") == "Ensure the embedding model is cached"
    )
    suite = next(i for i, s in enumerate(steps) if s.get("name") == "Run System Tests")
    assert cache < ensure < suite
    home = tmp_path / "home"
    env = os.environ.copy()
    env.pop("HF_HUB_CACHE", None)
    env.pop("HF_HOME", None)
    env["HOME"] = str(home)
    env["GITHUB_ENV"] = str(tmp_path / "github_env")
    env["UV_PROJECT_ENVIRONMENT"] = sys.prefix
    if selection == "hub":
        env["HF_HUB_CACHE"] = str(tmp_path / "hub")
        env["HF_HOME"] = str(tmp_path / "ignored")
        expected = tmp_path / "hub"
    elif selection == "home":
        env["HF_HOME"] = str(tmp_path / "hf")
        expected = tmp_path / "hf" / "hub"
    else:
        expected = home / ".cache" / "huggingface" / "hub"
    subprocess.run(steps[cache]["run"], shell=True, cwd=ROOT, env=env, check=True)
    name, value = Path(env["GITHUB_ENV"]).read_text().strip().split("=", 1)
    assert name == "HF_HUB_CACHE" and Path(value) == expected.resolve()
    model = expected / "models--sentence-transformers--all-MiniLM-L6-v2"
    (model / "refs").mkdir(parents=True)
    (model / "refs" / "main").write_text("revision")
    snapshot = model / "snapshots" / "revision"
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").write_bytes(b"weights")
    env[name] = value
    env["HOME"] = str(tmp_path / "isolated")
    probe = "from indexed.core.v1.engine.indexes.embeddings.model_manager import _get_hf_cache_dir, is_model_cached; import sys; assert str(_get_hf_cache_dir()) == sys.argv[1]; assert is_model_cached('all-MiniLM-L6-v2')"
    subprocess.run([sys.executable, "-c", probe, value], cwd=ROOT, env=env, check=True)


def test_retrieval_preflight_precedes_both_sides_and_uses_pinned_cache():
    steps = _workflow("python-eval.yml")["jobs"]["retrieval-baseline"]["steps"]
    pin = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Pin retrieval model cache"
    )
    prepare = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Prepare retrieval model cache"
    )
    measure = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Measure captured base and merge result in this job"
    )
    corpus = next(i for i, step in enumerate(steps) if step.get("id") == "corpus")
    harness = next(i for i, step in enumerate(steps) if step.get("id") == "harness")
    assert corpus < pin and harness < pin < prepare < measure
    assert steps[pin]["id"] == "model_cache_pin"
    assert "steps.model_cache_pin.outcome == 'success'" in steps[prepare]["if"]
    assert "HF_HUB_CACHE" in steps[pin]["run"]
    assert "AutoTokenizer.from_pretrained" in steps[prepare]["run"]
    assert steps[prepare]["id"] == "model_preflight"
    assert "steps.model_preflight.outcome == 'success'" in steps[measure]["if"]
    assert "steps.model_cache_pin.outcome == 'success'" in steps[measure]["if"]


def test_retrieval_preflight_loads_tokenizer_before_chunker(
    tmp_path, monkeypatch, capsys
):
    import docling_core.transforms.chunker as chunker_module
    import docling_core.transforms.chunker.tokenizer.huggingface as hf_tokenizer_module
    import transformers
    from indexed.core.v1.engine.indexes.embeddings import model_manager
    from indexed.eval import runner
    from indexed.parsing import _model_window

    steps = _workflow("python-eval.yml")["jobs"]["retrieval-baseline"]["steps"]
    run = next(
        s["run"] for s in steps if s.get("name") == "Prepare retrieval model cache"
    )
    code = run.split("<<'PYCODE'\n", 1)[1].rsplit("\nPYCODE", 1)[0]
    calls = []

    class Tokenizer:
        vocab_size = 100

        def get_vocab(self):
            return {str(i): i for i in range(101)}

    class ModelConfig:
        vocab_size = 100

    token = Tokenizer()
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    monkeypatch.setattr(runner, "DEFAULT_MODEL", "embed")
    monkeypatch.setattr(_model_window, "DEFAULT_TOKENIZER_MODEL", "parser")

    def ensure(name):
        calls.append(("ensure", name))
        return str(tmp_path / (name + "-snapshot"))

    def load(name, *, local_files_only):
        assert local_files_only is True
        calls.append(("tokenizer", name))
        return token

    def wrapper(*, tokenizer, max_tokens):
        assert tokenizer is token
        calls.append(("wrapper", max_tokens))
        return token

    def chunker(*, tokenizer):
        assert tokenizer is token
        calls.append(("chunker", tokenizer))
        return object()

    monkeypatch.setattr(model_manager, "ensure_model", ensure)
    monkeypatch.setattr(
        transformers.AutoConfig,
        "from_pretrained",
        lambda name, *, local_files_only: ModelConfig(),
    )
    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", load)
    monkeypatch.setattr(hf_tokenizer_module, "HuggingFaceTokenizer", wrapper)
    monkeypatch.setattr(chunker_module, "HybridChunker", chunker)
    exec(compile(code, "workflow-preflight", "exec"), {})
    assert [call[0] for call in calls] == [
        "ensure",
        "ensure",
        "tokenizer",
        "wrapper",
        "chunker",
    ]
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["cache"] == str(tmp_path.resolve())
    assert receipt["embedding_model"] == "embed"
    assert receipt["tokenizer_model"] == "parser"
    assert receipt["vocab_size"] == 100 and receipt["actual_vocab_size"] == 101

    def unavailable(_name, *, local_files_only):
        raise OSError("tokenizer missing")

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", unavailable)
    with pytest.raises(OSError, match="tokenizer missing"):
        exec(compile(code, "workflow-preflight", "exec"), {})

    class IncompleteTokenizer:
        vocab_size = 5

        def get_vocab(self):
            return {str(i): i for i in range(5)}

    monkeypatch.setattr(
        transformers.AutoTokenizer,
        "from_pretrained",
        lambda name, *, local_files_only: IncompleteTokenizer(),
    )
    monkeypatch.setattr(
        hf_tokenizer_module, "HuggingFaceTokenizer", lambda **kwargs: token
    )
    with pytest.raises(ValueError, match="vocab"):
        exec(compile(code, "workflow-preflight", "exec"), {})

    IncompleteTokenizer.vocab_size = 100
    with pytest.raises(ValueError, match="vocab"):
        exec(compile(code, "workflow-preflight", "exec"), {})
    ModelConfig.vocab_size = True
    with pytest.raises(ValueError, match="vocab"):
        exec(compile(code, "workflow-preflight", "exec"), {})


def test_retrieval_cache_pin_survives_home_isolation(tmp_path):
    steps = _workflow("python-eval.yml")["jobs"]["retrieval-baseline"]["steps"]
    step = next(s for s in steps if s.get("name") == "Pin retrieval model cache")
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "initial-home")
    env["RUNNER_TEMP"] = str(tmp_path / "runner")
    env["GITHUB_ENV"] = str(tmp_path / "github-env")
    env["UV_PROJECT_ENVIRONMENT"] = sys.prefix
    subprocess.run(step["run"], shell=True, cwd=ROOT, env=env, check=True)
    pinned = dict(
        line.split("=", 1) for line in Path(env["GITHUB_ENV"]).read_text().splitlines()
    )
    assert Path(pinned["HF_HOME"]) == (tmp_path / "runner/indexed-eval-hf").resolve()
    assert Path(pinned["HF_HUB_CACHE"]) == Path(pinned["HF_HOME"]) / "hub"
    env.update(pinned)
    env["HOME"] = str(tmp_path / "other-home")
    probe = "from indexed.core.v1.engine.indexes.embeddings.model_manager import _get_hf_cache_dir; import sys; assert str(_get_hf_cache_dir()) == sys.argv[1]"
    subprocess.run(
        [sys.executable, "-c", probe, pinned["HF_HUB_CACHE"]],
        cwd=ROOT,
        env=env,
        check=True,
    )
