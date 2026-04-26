"""Tests to ensure heavy dependencies are not eagerly imported.

The ``indexed init`` command and other lightweight operations must not
trigger imports of heavy packages like ``parsing`` (which pulls in
Docling, tree-sitter, etc.).  These tests guard against regressions
where module-level imports accidentally reintroduce eager loading.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch


class TestModelManagerImportChain:
    """Importing model_manager must NOT drag in the parsing package."""

    def test_model_manager_does_not_import_parsing(self):
        """Verify that importing model_manager doesn't load 'parsing'."""
        # Remove parsing from sys.modules if previously loaded so we can
        # detect a fresh import triggered by model_manager.
        previously_loaded = "parsing" in sys.modules
        saved = sys.modules.pop("parsing", None)
        try:
            # Re-import to trigger the full import chain
            mod = importlib.import_module(
                "core.v1.engine.indexes.embeddings.model_manager"
            )
            assert mod is not None
            # parsing should NOT have been pulled in as a side-effect
            assert "parsing" not in sys.modules, (
                "Importing model_manager eagerly loaded the 'parsing' package. "
                "This causes 'indexed init' to fail when parsing deps are missing."
            )
        finally:
            # Restore previous state
            if previously_loaded and saved is not None:
                sys.modules["parsing"] = saved


class TestConnectorImportChain:
    """Importing the connectors package must not fail due to parsing."""

    def test_connectors_package_importable(self):
        """The connectors package should import without errors."""
        mod = importlib.import_module("connectors")
        assert mod is not None

    def test_files_connector_importable(self):
        """The files connector should import without errors."""
        mod = importlib.import_module("connectors.files.connector")
        assert mod is not None

    def test_files_document_reader_importable(self):
        """FilesDocumentReader should import without eagerly loading parsing."""
        previously_loaded = "parsing" in sys.modules
        saved = sys.modules.pop("parsing", None)
        try:
            # Force reimport of the reader module
            key = "connectors.files.files_document_reader"
            sys.modules.pop(key, None)
            mod = importlib.import_module(key)
            assert mod is not None
            assert "parsing" not in sys.modules, (
                "Importing files_document_reader eagerly loaded 'parsing'. "
                "The parsing import should be lazy (inside a property or method)."
            )
        finally:
            if previously_loaded and saved is not None:
                sys.modules["parsing"] = saved


class TestInitCommandImportChain:
    """The init command must work without parsing being available."""

    def test_init_skip_model_succeeds(self):
        """indexed init --skip-model should not require parsing at all."""
        from typer.testing import CliRunner

        from indexed.app import app

        runner = CliRunner()

        with patch(
            "core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
            return_value={
                "cache_dir": "/tmp/hf",
                "models": [],
                "total_size_mb": 0,
            },
        ):
            result = runner.invoke(app, ["init", "--skip-model"])
            assert result.exit_code == 0, (
                f"init --skip-model failed (exit {result.exit_code}):\n{result.output}"
            )
