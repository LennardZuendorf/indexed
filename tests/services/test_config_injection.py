import os
from typing import Any, Dict

import pytest

from main.services import resolve_and_extract, ConfigSlice
from main.services.models import SourceConfig
from main.services.search_service import SearchArgs
from main.services.inspect_service import InspectArgs


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    # Clear relevant env to avoid leakage between tests
    keys = [
        "INDEXED__SEARCH__MAX_DOCS",
        "INDEXED__SEARCH__MAX_CHUNKS",
        "INDEXED__SEARCH__INCLUDE_FULL_TEXT",
        "INDEXED__SEARCH__INCLUDE_ALL_CHUNKS",
        "INDEXED__SEARCH__INCLUDE_MATCHED_CHUNKS",
    ]
    saved: Dict[str, Any] = {k: os.environ.get(k) for k in keys}
    for k in keys:
        if k in os.environ:
            monkeypatch.delenv(k, raising=False)
    yield
    # restore
    for k, v in saved.items():
        if v is not None:
            monkeypatch.setenv(k, v)


def test_search_slice_env_and_overrides(monkeypatch):
    # Env-provided defaults
    monkeypatch.setenv("INDEXED__SEARCH__MAX_DOCS", "7")
    monkeypatch.setenv("INDEXED__SEARCH__MAX_CHUNKS", "50")
    monkeypatch.setenv("INDEXED__SEARCH__INCLUDE_FULL_TEXT", "true")

    # Overrides should take precedence over env/TOML/defaults
    _settings, args = resolve_and_extract(
        ConfigSlice.SEARCH,
        overrides={
            "max_docs": 5,  # precedence over env (7)
        },
    )

    assert isinstance(args, SearchArgs)
    assert args.max_docs == 5
    # max_chunks from env (50) since we didn't override
    assert args.max_chunks == 50
    assert args.include_full_text is True
    # default configs: auto-discovery
    assert args.configs is None


def test_search_slice_single_collection_overrides():
    _settings, args = resolve_and_extract(
        ConfigSlice.SEARCH,
        overrides={
            "collection": "c1",
            "index_name": "idx",
        },
    )
    assert isinstance(args, SearchArgs)
    assert args.configs is not None and len(args.configs) == 1
    cfg = args.configs[0]
    assert isinstance(cfg, SourceConfig)
    assert cfg.name == "c1"
    assert cfg.indexer == "idx"


def test_inspect_slice_override_only():
    _settings, args = resolve_and_extract(
        ConfigSlice.INSPECT,
        overrides={"include_index_size": True},
    )
    assert isinstance(args, InspectArgs)
    assert args.include_index_size is True


def test_create_update_slice_with_configs():
    cfg = SourceConfig(
        name="x",
        type="localFiles",
        base_url_or_path="",
        indexer="idx",
    )

    _settings, create_args = resolve_and_extract(
        ConfigSlice.CREATE,
        overrides={"configs": [cfg], "use_cache": False, "force": True},
    )
    assert create_args.configs == [cfg]
    assert create_args.use_cache is False
    assert create_args.force is True

    _settings, update_args = resolve_and_extract(
        ConfigSlice.UPDATE,
        overrides={"configs": [cfg]},
    )
    assert update_args.configs == [cfg]



