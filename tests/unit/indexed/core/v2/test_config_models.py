"""Unit tests for v2 config models (core-v2/2a).

tech.md §"Config" defines ``[core.v2.embedding]``/``[core.v2.search]`` only —
no ``[core.v2.storage]`` (the manifest's ``vectorStore`` field is the seam)
and no ``[core.v2.rerank]`` (core-v2/6). See task report for the plan.md
wording-gap note.
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


def test_no_storage_or_rerank_config_models_exist() -> None:
    import indexed.core.v2.config_models as config_models

    names = {n.lower() for n in dir(config_models)}
    assert not any("storage" in n for n in names)
    assert not any("rerank" in n for n in names)
