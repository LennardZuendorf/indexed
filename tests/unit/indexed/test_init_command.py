"""Tests for the `indexed init` CLI command."""

import re
from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


def _get_app():
    from indexed.app import app

    return app


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestInitCommand:
    def test_appears_in_help(self):
        result = runner.invoke(_get_app(), ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output

    def test_has_own_help(self):
        result = runner.invoke(_get_app(), ["init", "--help"])
        assert result.exit_code == 0
        clean = _strip_ansi(result.output)
        assert "--model" in clean
        assert "--force" in clean
        assert "--skip-model" in clean

    def test_skips_download_when_cached(self):
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager.is_model_cached",
            return_value=True,
        ):
            with patch(
                "core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                return_value={
                    "cache_dir": "/tmp/hf",
                    "models": [{"name": "st/m", "size_mb": 80, "path": "/tmp/hf/m"}],
                    "total_size_mb": 80,
                },
            ):
                result = runner.invoke(_get_app(), ["init"])
                assert result.exit_code == 0
                assert "already" in result.output.lower()

    def test_downloads_when_not_cached(self):
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager.is_model_cached",
            return_value=False,
        ):
            with patch(
                "core.v1.engine.indexes.embeddings.model_manager.ensure_model"
            ) as mock_dl:
                mock_dl.return_value = "/tmp/hf/snapshot"
                with patch(
                    "core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                    return_value={
                        "cache_dir": "/tmp/hf",
                        "models": [],
                        "total_size_mb": 0,
                    },
                ):
                    result = runner.invoke(_get_app(), ["init"])
                    assert result.exit_code == 0
                    mock_dl.assert_called_once()

    def test_force_redownloads(self):
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager.is_model_cached",
            return_value=True,
        ):
            with patch(
                "core.v1.engine.indexes.embeddings.model_manager.ensure_model"
            ) as mock_dl:
                mock_dl.return_value = "/tmp/hf/snapshot"
                with patch(
                    "core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                    return_value={
                        "cache_dir": "/tmp/hf",
                        "models": [],
                        "total_size_mb": 0,
                    },
                ):
                    result = runner.invoke(_get_app(), ["init", "--force"])
                    assert result.exit_code == 0
                    mock_dl.assert_called_once()

    def test_skip_model(self):
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager.ensure_model"
        ) as mock_dl:
            with patch(
                "core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                return_value={
                    "cache_dir": "/tmp/hf",
                    "models": [],
                    "total_size_mb": 0,
                },
            ):
                result = runner.invoke(_get_app(), ["init", "--skip-model"])
                assert result.exit_code == 0
                mock_dl.assert_not_called()

    def test_custom_model(self):
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager.is_model_cached",
            return_value=False,
        ):
            with patch(
                "core.v1.engine.indexes.embeddings.model_manager.ensure_model"
            ) as mock_dl:
                mock_dl.return_value = "/tmp/hf/snap"
                with patch(
                    "core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                    return_value={
                        "cache_dir": "/tmp/hf",
                        "models": [],
                        "total_size_mb": 0,
                    },
                ):
                    result = runner.invoke(
                        _get_app(), ["init", "-m", "all-mpnet-base-v2"]
                    )
                    assert result.exit_code == 0
                    mock_dl.assert_called_once_with("all-mpnet-base-v2", force=False)

    def test_idempotent(self):
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager.is_model_cached",
            return_value=True,
        ):
            with patch(
                "core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                return_value={
                    "cache_dir": "/tmp/hf",
                    "models": [{"name": "st/m", "size_mb": 80, "path": "/p"}],
                    "total_size_mb": 80,
                },
            ):
                app = _get_app()
                r1 = runner.invoke(app, ["init"])
                r2 = runner.invoke(app, ["init"])
                assert r1.exit_code == 0
                assert r2.exit_code == 0
