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
