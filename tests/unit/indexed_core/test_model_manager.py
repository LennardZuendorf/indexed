"""Tests for model_manager — HuggingFace cache-aware model management."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_hf_cache_structure(
    tmp_path: Path, model_name: str = "all-MiniLM-L6-v2"
) -> Path:
    """Create a realistic HuggingFace hub cache directory for a model."""
    repo_dir = tmp_path / f"models--sentence-transformers--{model_name}"
    blobs = repo_dir / "blobs"
    refs = repo_dir / "refs"
    snap = repo_dir / "snapshots" / "abc123deadbeef"

    blobs.mkdir(parents=True)
    refs.mkdir(parents=True)
    snap.mkdir(parents=True)

    (blobs / "fakehash1").write_text("{}")
    (blobs / "fakehash2").write_bytes(b"\x00" * 1024)
    (snap / "config.json").write_text('{"model_type": "bert"}')
    (snap / "model.safetensors").write_bytes(b"\x00" * 2048)
    (refs / "main").write_text("abc123deadbeef")

    return repo_dir


class TestGetHfCacheDir:
    def test_default_location(self):
        from core.v1.engine.indexes.embeddings.model_manager import _get_hf_cache_dir

        with patch.dict("os.environ", {}, clear=True):
            result = _get_hf_cache_dir()
            assert result == Path.home() / ".cache" / "huggingface" / "hub"

    def test_respects_hf_hub_cache_env(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import _get_hf_cache_dir

        with patch.dict("os.environ", {"HF_HUB_CACHE": str(tmp_path)}):
            assert _get_hf_cache_dir() == tmp_path

    def test_respects_hf_home_env(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import _get_hf_cache_dir

        with patch.dict("os.environ", {"HF_HOME": str(tmp_path)}, clear=True):
            result = _get_hf_cache_dir()
            assert result == tmp_path / "hub"

    def test_hf_hub_cache_takes_priority(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import _get_hf_cache_dir

        custom = tmp_path / "custom"
        with patch.dict(
            "os.environ",
            {"HF_HUB_CACHE": str(custom), "HF_HOME": str(tmp_path / "other")},
        ):
            assert _get_hf_cache_dir() == custom


class TestModelRepoId:
    def test_short_name_gets_prefixed(self):
        from core.v1.engine.indexes.embeddings.model_manager import _model_repo_id

        assert (
            _model_repo_id("all-MiniLM-L6-v2")
            == "sentence-transformers/all-MiniLM-L6-v2"
        )

    def test_already_qualified_unchanged(self):
        from core.v1.engine.indexes.embeddings.model_manager import _model_repo_id

        assert _model_repo_id("custom-org/my-model") == "custom-org/my-model"


class TestIsModelCached:
    def test_false_when_nothing_exists(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False

    def test_false_when_dir_exists_but_no_snapshots(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        model_dir = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        model_dir.mkdir(parents=True)
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False

    def test_false_when_snapshots_empty(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        model_dir = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        (model_dir / "snapshots" / "abc123").mkdir(parents=True)
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False

    def test_true_when_properly_cached(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is True

    def test_handles_custom_org_model(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        model_dir = tmp_path / "models--custom-org--my-model"
        snap = model_dir / "snapshots" / "abc123"
        snap.mkdir(parents=True)
        (snap / "config.json").write_text("{}")
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("custom-org/my-model") is True


class TestResolveSnapshotPath:
    def test_resolves_via_refs_main(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
        )

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            path = _resolve_snapshot_path("all-MiniLM-L6-v2")
            assert "abc123deadbeef" in path

    def test_fallback_to_first_snapshot(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
        )

        repo = _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        (repo / "refs" / "main").unlink()
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            path = _resolve_snapshot_path("all-MiniLM-L6-v2")
            assert Path(path).exists()

    def test_raises_when_no_valid_snapshot(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
        )

        model_dir = tmp_path / "models--sentence-transformers--broken-model"
        (model_dir / "snapshots").mkdir(parents=True)
        (model_dir / "refs").mkdir(parents=True)
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with pytest.raises(FileNotFoundError, match="no valid snapshot"):
                _resolve_snapshot_path("broken-model")


class TestEnsureModel:
    def test_skips_download_when_cached(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import ensure_model

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            path = ensure_model("all-MiniLM-L6-v2", force=False)
            assert "abc123deadbeef" in path

    def test_downloads_when_not_cached(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import ensure_model

        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "huggingface_hub.snapshot_download",
                return_value=str(tmp_path / "downloaded"),
            ) as mock_dl:
                ensure_model("all-MiniLM-L6-v2", force=False)
                mock_dl.assert_called_once_with(
                    repo_id="sentence-transformers/all-MiniLM-L6-v2"
                )

    def test_force_downloads_even_when_cached(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import ensure_model

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "huggingface_hub.snapshot_download",
                return_value=str(tmp_path / "re-dl"),
            ) as mock_dl:
                ensure_model("all-MiniLM-L6-v2", force=True)
                mock_dl.assert_called_once()


class TestLoadModel:
    def test_loads_with_local_files_only_when_cached(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        mock_model = MagicMock()
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_model,
            ) as mock_cls:
                result = load_model("all-MiniLM-L6-v2")
                mock_cls.assert_called_once_with(
                    "sentence-transformers/all-MiniLM-L6-v2",
                    local_files_only=True,
                )
                assert result is mock_model

    def test_warns_and_downloads_when_not_cached(self, tmp_path, caplog):
        from core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        mock_model = MagicMock()
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_model,
            ) as mock_cls:
                import logging

                with caplog.at_level(logging.WARNING):
                    load_model("not-cached-model")
                assert "not found in cache" in caplog.text
                mock_cls.assert_called_once_with(
                    "sentence-transformers/not-cached-model"
                )

    def test_lru_cache_returns_same_instance(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        mock_model = MagicMock()
        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_model,
            ):
                m1 = load_model("all-MiniLM-L6-v2")
                m2 = load_model("all-MiniLM-L6-v2")
                assert m1 is m2


class TestGetCacheInfo:
    def test_empty_cache(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import get_cache_info

        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            info = get_cache_info()
            assert info["models"] == []
            assert info["total_size_mb"] == 0

    def test_reports_cached_models_via_scan(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import get_cache_info

        mock_repo = MagicMock()
        mock_repo.repo_type = "model"
        mock_repo.repo_id = "sentence-transformers/all-MiniLM-L6-v2"
        mock_repo.size_on_disk = 80 * 1024 * 1024
        mock_repo.revisions = [MagicMock()]
        mock_repo.last_modified = 1711000000.0
        mock_repo.repo_path = (
            tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        )

        mock_cache = MagicMock()
        mock_cache.repos = [mock_repo]

        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch("huggingface_hub.scan_cache_dir", return_value=mock_cache):
                info = get_cache_info()
                assert len(info["models"]) == 1
                assert (
                    info["models"][0]["name"]
                    == "sentence-transformers/all-MiniLM-L6-v2"
                )
                assert info["models"][0]["size_mb"] == 80.0

    def test_filters_non_st_models(self, tmp_path):
        from core.v1.engine.indexes.embeddings.model_manager import get_cache_info

        st_repo = MagicMock()
        st_repo.repo_type = "model"
        st_repo.repo_id = "sentence-transformers/all-MiniLM-L6-v2"
        st_repo.size_on_disk = 80 * 1024 * 1024
        st_repo.revisions = [MagicMock()]
        st_repo.last_modified = 1711000000.0
        st_repo.repo_path = tmp_path / "st"

        other_repo = MagicMock()
        other_repo.repo_type = "model"
        other_repo.repo_id = "openai/whisper-large"
        other_repo.size_on_disk = 3000 * 1024 * 1024

        mock_cache = MagicMock()
        mock_cache.repos = [st_repo, other_repo]

        with patch(
            "core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch("huggingface_hub.scan_cache_dir", return_value=mock_cache):
                info = get_cache_info()
                assert len(info["models"]) == 1
