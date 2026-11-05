#!/usr/bin/env python3
"""Run one genuine side with explicitly captured common evaluator instrumentation."""

from __future__ import annotations

import argparse
from hashlib import sha256
import importlib
import importlib.util
import inspect
import json
import os
import stat
import tempfile
from pathlib import Path
import subprocess
from typing import Any, cast

HELPER = Path(__file__).resolve().parents[1] / "src/indexed/eval/canonical.py"


def side_provenance(root: Path) -> dict[str, Any]:
    """Fail explicitly if any measured implementation comes from another side."""
    origins = {}
    for name in (
        "indexed",
        "indexed.eval.runner",
        "indexed.core",
        "indexed.parsing",
        "indexed.connectors.files.connector",
    ):
        origin = Path(cast(str, importlib.import_module(name).__file__)).resolve()
        if not origin.is_relative_to(root.resolve()):
            raise ValueError(
                f"{name} imported from {origin}, outside measured side {root}"
            )
        origins[name] = str(origin)
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    return {
        "engine_revision": revision,
        "import_origins": origins,
        "lock_sha256": sha256((root / "uv.lock").read_bytes()).hexdigest(),
    }


def measure(root: Path, harness_revision: str, engine_revision: str) -> dict[str, Any]:
    """Use the existing factory injection API, including on pre-policy runners."""
    provenance = side_provenance(root)
    if provenance["engine_revision"] != engine_revision:
        raise ValueError("measured engine revision differs from captured revision")
    runner = importlib.import_module("indexed.eval.runner")
    if "connector_factory" not in inspect.signature(runner.run_eval).parameters:
        raise ValueError("measured evaluator lacks connector_factory injection")
    spec = importlib.util.spec_from_file_location(
        "_indexed_eval_common_canonical", HELPER
    )
    if spec is None or spec.loader is None:
        raise ValueError("common evaluator helper is unavailable")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    factory = helper.CanonicalFactory(root / "eval/corpus")
    report = runner.run_eval(
        cases_path=root / "eval/cases.json",
        corpus_dir=root / "eval/corpus",
        corpus_manifest=root / "eval/corpus.json",
        connector_factory=factory,
    )
    report["config"]["input_context_policy"] = helper.POLICY
    report["environment"]["converter_inputs"] = factory.evidence()
    harness_root = Path(__file__).resolve().parents[1]
    actual_harness_revision = subprocess.check_output(
        ["git", "-C", str(harness_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_harness_revision != harness_revision:
        raise ValueError(
            "common harness checkout differs from captured harness revision"
        )
    matches_revision = True
    for path in (Path(__file__).resolve(), HELPER):
        original = subprocess.run(
            [
                "git",
                "-C",
                str(harness_root),
                "show",
                f"{harness_revision}:{path.relative_to(harness_root)}",
            ],
            capture_output=True,
            check=False,
        )
        matches_revision = (
            matches_revision
            and original.returncode == 0
            and original.stdout == path.read_bytes()
        )
    report["environment"]["common_harness"] = {
        "revision": harness_revision,
        "policy": helper.POLICY,
        "content_matches_revision": matches_revision,
        "instrumentation_status": "captured-commit"
        if matches_revision
        else "uncommitted-overlay",
        "files_sha256": {
            "launcher": sha256(Path(__file__).read_bytes()).hexdigest(),
            "canonical_helper": sha256(HELPER.read_bytes()).hexdigest(),
        },
        **provenance,
    }
    return report


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Replace a declared regular report through an exclusive temporary file."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(mode):
            raise ValueError(f"report output must be a regular file: {path}")
    payload = json.dumps(report, allow_nan=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--harness-revision", required=True)
    parser.add_argument("--engine-revision", required=True)
    args = parser.parse_args()
    report = measure(args.root.resolve(), args.harness_revision, args.engine_revision)
    write_report(args.out, report)


if __name__ == "__main__":
    main()
