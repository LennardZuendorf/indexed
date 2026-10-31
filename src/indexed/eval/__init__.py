"""Retrieval evaluation harness (issue #204).

Turns "search feels better" into numbers: a pinned corpus + a pinned case set
plus deterministic hit-rate@k / MRR arithmetic, and a committed baseline the next
retrieval change is compared against.

Layering: this package sits ABOVE ``indexed.core`` and consumes it only through
the ``indexed.core.engine`` facade — the same entry point the CLI and the MCP
server use — so it measures the retrieval contract rather than a private path.
"""

from __future__ import annotations

from indexed.eval.cases import Case, CaseSet, load_case_set
from indexed.eval.compare import compare_reports
from indexed.eval.metrics import aggregate, score_case

__all__ = [
    "Case",
    "CaseSet",
    "aggregate",
    "compare_reports",
    "load_case_set",
    "score_case",
]
