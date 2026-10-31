"""Validate saved retrieval reports against their recorded evidence."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from indexed.eval.metrics import aggregate, score_case

REPORT_SCHEMA = "indexed.eval.report.v1"


class ReportValidationError(ValueError):
    """A saved report cannot support a comparison."""


def _require(condition: bool, message: str) -> None:
    """Reject report evidence that violates a comparison precondition."""
    if not condition:
        raise ReportValidationError(message)


def _text(value: Any) -> bool:
    """Accept strings containing at least one non-whitespace character."""
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> bool:
    """Accept integers and finite floats, excluding booleans."""
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _finite_config(value: Any) -> bool:
    """Check numeric settings recursively, including future additive fields."""
    if isinstance(value, dict):
        return all(_finite_config(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite_config(item) for item in value)
    return type(value) is not float or math.isfinite(value)


def _matches(value: Any, expected: Any) -> bool:
    """Compare canonical values without treating booleans as numeric measurements."""
    if type(expected) is float:
        return _number(value) and value == expected
    return type(value) is type(expected) and value == expected


def _strings(value: Any) -> bool:
    """Accept lists whose entries are nonblank strings."""
    return isinstance(value, list) and all(_text(item) for item in value)


def _validate_case(record: Any, k: int) -> Dict[str, Any]:
    """Check stored evidence and derive its canonical arithmetic independently."""
    _require(isinstance(record, dict), "query record must be an object")
    for key in ("id", "query", "provenance", "rationale"):
        _require(_text(record.get(key)), f"query {key} must be a nonempty string")
    for key in ("ranked_docs", "relevant", "distractors"):
        _require(
            _strings(record.get(key)),
            f"query {record['id']} {key} must be a string list",
        )
        _require(
            len(record[key]) == len(set(record[key])),
            f"query {record['id']} has duplicate {key}",
        )
    _require(
        not set(record["relevant"]) & set(record["distractors"]),
        "query judgments overlap",
    )
    _require(
        type(record.get("k")) is int and record["k"] == k,
        "query k differs from metrics k",
    )
    _require(
        _number(record.get("elapsed_ms")) and record["elapsed_ms"] >= 0,
        "query elapsed_ms must be finite and nonnegative",
    )
    _require(
        "error" in record and (record["error"] is None or _text(record["error"])),
        "query error must be null or a nonempty string",
    )
    ranking = record.get("ranking")
    _require(isinstance(ranking, list), "query ranking must be a list")
    _require(
        len(ranking) == len(record["ranked_docs"]),
        "query ranking contradicts ranked_docs",
    )
    for rank, (detail, doc) in enumerate(zip(ranking, record["ranked_docs"]), 1):
        _require(isinstance(detail, dict), "ranking entry must be an object")
        _require(
            type(detail.get("rank")) is int
            and detail["rank"] == rank
            and detail.get("doc") == doc,
            "query ranking contradicts ranked_docs",
        )
        _require(
            type(detail.get("chunk")) is int and detail["chunk"] >= -1,
            "ranking chunk must be an integer >= -1",
        )
        _require(_number(detail.get("score")), "ranking score must be finite")
        _require(
            isinstance(detail.get("score_kind"), str),
            "ranking score_kind must be a string",
        )
    canonical = score_case(
        case_id=record["id"],
        query=record["query"],
        ranked_doc_ids=record["ranked_docs"],
        relevant=record["relevant"],
        distractors=record["distractors"],
        k=k,
        error=record["error"],
    )
    for key in (
        "status",
        "first_relevant_rank",
        "reciprocal_rank",
        "hit_at_k",
        "distractor_leak",
    ):
        _require(
            key in record and _matches(record[key], canonical[key]),
            f"query {record['id']} {key} contradicts saved ranking and judgments",
        )
    return canonical


def _validate_report(report: Any) -> None:
    """Reconcile report claims only after checking every consumed field's type."""
    _require(isinstance(report, dict), "report must be an object")
    _require(
        report.get("schema") == REPORT_SCHEMA, f"report schema must be {REPORT_SCHEMA}"
    )
    _require(
        _text(report.get("generated_at")), "generated_at must be a nonempty string"
    )
    for key in ("corpus", "case_set", "config", "metrics", "environment"):
        _require(isinstance(report.get(key), dict), f"{key} must be an object")
    environment = report["environment"]
    for key in ("python", "platform", "indexed_version"):
        _require(
            _text(environment.get(key)), f"environment.{key} must be a nonempty string"
        )
    cache = environment.get("embedding_model_cache")
    _require(
        isinstance(cache, dict), "environment.embedding_model_cache must be an object"
    )
    _require(
        _text(cache.get("cache_dir")),
        "embedding model cache_dir must be a nonempty string",
    )
    _require(
        type(cache.get("present")) is bool and _strings(cache.get("weights")),
        "embedding model cache must record boolean present and weights list",
    )
    for section, key in (("corpus", "tree_sha256"), ("case_set", "sha256")):
        value = report[section].get(key)
        _require(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            f"{section}.{key} must be a SHA256 hash",
        )
    _require(
        _text(report["corpus"].get("source_repo_rev")),
        "corpus.source_repo_rev must be a nonempty string",
    )
    files = report["corpus"].get("files")
    _require(isinstance(files, list), "corpus.files must be a list")
    for file in files:
        _require(
            isinstance(file, dict)
            and _text(file.get("path"))
            and _text(file.get("source")),
            "corpus file must name path and source",
        )
        _require(
            isinstance(file.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", file["sha256"]) is not None,
            "corpus file sha256 must be a SHA256 hash",
        )
    _require(
        _text(report["case_set"].get("path")), "case_set.path must be a nonempty string"
    )
    config, metrics = report["config"], report["metrics"]
    _require(_finite_config(config), "config numbers must be finite")
    for key in ("engine", "embedding_model"):
        _require(_text(config.get(key)), f"config.{key} must be a nonempty string")
    _require(config["engine"] in {"1", "2"}, "config.engine must be 1 or 2")
    _require(
        isinstance(config.get("score_kind"), str), "config.score_kind must be a string"
    )
    _require(type(config.get("rerank")) is bool, "config.rerank must be boolean")
    for key in ("top_k", "max_docs"):
        _require(
            type(config.get(key)) is int and config[key] > 0,
            f"config.{key} must be a positive integer",
        )
    _require(config["top_k"] <= config["max_docs"], "config.top_k exceeds max_docs")
    k = metrics.get("k")
    _require(
        type(k) is int and k > 0 and k == config["top_k"],
        "metrics.k must equal config.top_k",
    )
    queries = report.get("queries")
    _require(isinstance(queries, list), "queries must be a list")
    canonical = [_validate_case(record, k) for record in queries]
    ids = [record["id"] for record in canonical]
    _require(len(ids) == len(set(ids)), "query IDs must be unique")
    _require(
        type(report["case_set"].get("cases")) is int
        and report["case_set"]["cases"] == len(queries),
        "case_set.cases contradicts query count",
    )
    rebuilt = aggregate(canonical, k)
    for key, expected in rebuilt.items():
        value = metrics.get(key)
        _require(
            key in metrics and _matches(value, expected),
            f"metrics.{key} contradicts saved query records",
        )
    expected_failures = [
        {"id": record["id"], "error": record["error"]}
        for record in canonical
        if record["error"]
    ]
    _require(
        report.get("failures") == expected_failures,
        "failures contradict saved query errors",
    )


def report_problems(report: Any, label: str) -> List[str]:
    """Return a precise data diagnostic without masking implementation errors."""
    try:
        _validate_report(report)
    except ReportValidationError as exc:
        return [f"{label}: {exc}"]
    return []
