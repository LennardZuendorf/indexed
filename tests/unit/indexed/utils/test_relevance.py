"""Tests for the shared relevance-scoring helper (issue #186 dedup + fix)."""

from __future__ import annotations

import math

from indexed.utils.relevance import HIGHER_IS_BETTER, unified_relevance


def test_higher_is_better_contains_cosine_and_rerank() -> None:
    assert HIGHER_IS_BETTER == frozenset({"cosine", "rerank"})


def test_cosine_score_passes_through_unchanged() -> None:
    assert unified_relevance(0.75, "cosine") == 0.75


def test_l2_squared_score_maps_to_cosine_similarity() -> None:
    # sim = 1 - d^2/2
    assert unified_relevance(0.1, "l2_squared") == 1.0 - 0.1 / 2.0
    assert unified_relevance(0.1, "") == 1.0 - 0.1 / 2.0  # v1 has no scoreKind at all


def test_rerank_score_is_bounded_regardless_of_raw_magnitude() -> None:
    """issue #186: unbounded cross-encoder logits (measured -11 to +6) must
    land in a comparable (0, 1) range instead of overwhelming/underwhelming
    the [0,1] cosine scale when sorted together."""
    high = unified_relevance(6.27, "rerank")
    low = unified_relevance(-11.0, "rerank")

    assert 0.0 < high < 1.0
    assert 0.0 < low < 1.0
    assert high > low  # monotonic: order among rerank scores is preserved
    assert high == 1.0 / (1.0 + math.exp(-6.27))
