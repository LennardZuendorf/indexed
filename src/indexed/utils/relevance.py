"""Shared cross-engine relevance scoring (issue #186 — was duplicated
verbatim between mcp/formatting.py and cli/knowledge/commands/search_render.py).

Pure arithmetic, engine-agnostic: no core.v1/core.v2 import, so both the CLI
and MCP formatters (top-layer consumers) can import it directly.
"""

from __future__ import annotations

import math

# Score kinds (v2's per-collection "scoreKind" field) for which a HIGHER
# score is a BETTER match. v1 results carry no "scoreKind" key at all, so a
# plain `.get()` defaults a v1 collection out of this set — its sort key
# stays the raw ascending distance, unchanged. "rerank" is a cross-encoder
# relevance (also higher-is-better) reported when
# [core.v2.rerank] enabled=true replaces the cosine score.
HIGHER_IS_BETTER = frozenset({"cosine", "rerank"})


def unified_relevance(raw_score: float, score_kind: str) -> float:
    """Map a raw per-engine/per-mode score onto one comparable (0, 1) measure.

    - "cosine" (v2, rerank disabled): already a bounded similarity in [0,1] —
      the raw score IS the relevance, unchanged.
    - "rerank" (v2 with [core.v2.rerank] enabled): an UNBOUNDED cross-encoder
      logit (measured -11 to +6) — squashed through a sigmoid so it lands in
      (0,1), comparable to cosine/l2_squared instead of overwhelming or
      underwhelming them when sorted together (issue #186).
    - anything else ("l2_squared"/v1, or absent): v1's squared-L2 distance
      d^2 over unit-normalized vectors — sim = 1 - d^2/2 recovers the cosine
      exactly.
    """
    if score_kind == "rerank":
        return 1.0 / (1.0 + math.exp(-raw_score))
    if score_kind in HIGHER_IS_BETTER:  # "cosine"
        return raw_score
    return 1.0 - raw_score / 2.0


__all__ = ["HIGHER_IS_BETTER", "unified_relevance"]
