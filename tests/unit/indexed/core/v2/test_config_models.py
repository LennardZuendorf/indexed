"""Unit tests for v2 config models (core-v2/2a, +2/6 rerank).

tech.md §"Config" defines ``[core.v2.embedding]``, ``[core.v2.search]`` and
``[core.v2.rerank]`` — but no ``[core.v2.storage]`` (the manifest's
``vectorStore`` field is the store-identity seam).
"""

from __future__ import annotations


def test_embedding_config_defaults_match_v1_model() -> None:
    from indexed.core.v2.config_models import CoreV2EmbeddingConfig

    cfg = CoreV2EmbeddingConfig()
    assert cfg.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.batch_size == 32


def test_search_config_defaults() -> None:
    from indexed.core.v2.config_models import CoreV2SearchConfig

    cfg = CoreV2SearchConfig()
    assert cfg.max_docs == 10
    assert cfg.score_threshold == 0.0


def test_rerank_config_defaults_disabled() -> None:
    """R10: rerank is OFF by default with the ms-marco cross-encoder + top_n=10."""
    from indexed.core.v2.config_models import CoreV2RerankConfig

    cfg = CoreV2RerankConfig()
    assert cfg.enabled is False
    assert cfg.model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert cfg.top_n == 10


def test_no_storage_config_model_exists() -> None:
    import indexed.core.v2.config_models as config_models

    names = {n.lower() for n in dir(config_models)}
    assert not any("storage" in n for n in names)
