"""Regression: core service modules must not bootstrap logging at import time."""

from __future__ import annotations

import importlib

import pytest
from loguru import logger


@pytest.fixture
def clean_loguru_handlers():
    """Remove all loguru sinks so import side effects are observable."""
    logger.remove()
    yield
    logger.remove()


def test_import_collection_service_does_not_add_handlers(clean_loguru_handlers):
    from indexed.core.v1.engine.services import collection_service

    before = len(logger._core.handlers)
    importlib.reload(collection_service)
    assert len(logger._core.handlers) == before


def test_import_inspect_service_does_not_add_handlers(clean_loguru_handlers):
    from indexed.core.v1.engine.services import inspect_service

    before = len(logger._core.handlers)
    importlib.reload(inspect_service)
    assert len(logger._core.handlers) == before
