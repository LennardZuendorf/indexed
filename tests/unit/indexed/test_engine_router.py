"""Unit tests for the engine router."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from indexed.services.engine_router import (
    GeneralConfig,
    detect_collection_engine,
    get_collection_service,
    get_effective_engine,
    get_inspect_service,
    get_search_service,
)


class TestGeneralConfig:
    def test_defaults_to_v1(self) -> None:
        cfg = GeneralConfig()
        assert cfg.engine == "v1"

    def test_accepts_v2(self) -> None:
        cfg = GeneralConfig(engine="v2")
        assert cfg.engine == "v2"

    def test_rejects_invalid_engine(self) -> None:
        with pytest.raises(Exception):
            GeneralConfig(engine="v3")


class TestGetEffectiveEngine:
    def test_command_flag_wins_over_everything(self) -> None:
        """Per-command --engine flag is the highest priority."""
        with patch("click.get_current_context") as mock_ctx:
            mock_ctx.return_value.obj = {"engine": "v1"}
            assert get_effective_engine("v2") == "v2"

    def test_command_flag_lowercases(self) -> None:
        assert get_effective_engine("V2") == "v2"

    def test_root_flag_from_ctx_obj(self) -> None:
        """Root callback engine stored in ctx.obj is second priority."""
        mock_ctx = MagicMock()
        mock_ctx.obj = {"engine": "v2"}
        with patch("click.get_current_context", return_value=mock_ctx):
            assert get_effective_engine(None) == "v2"

    def test_no_ctx_obj_falls_through(self) -> None:
        """When ctx.obj has no engine key, falls through to config."""
        mock_ctx = MagicMock()
        mock_ctx.obj = {}
        with patch("click.get_current_context", return_value=mock_ctx):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("no config")
                result = get_effective_engine(None)
        assert result == "v1"

    def test_runtime_error_falls_through_to_config(self) -> None:
        """RuntimeError from missing Click context is handled."""
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("no config")
                assert get_effective_engine(None) == "v1"

    def test_attribute_error_falls_through(self) -> None:
        """AttributeError (tests call without Typer context) is handled."""
        with patch("click.get_current_context", side_effect=AttributeError("no attr")):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("no config")
                assert get_effective_engine(None) == "v1"

    def test_config_engine_v2(self) -> None:
        """[general] engine = "v2" in config.toml is third priority."""
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            mock_svc = MagicMock()
            mock_provider = MagicMock()
            mock_svc.bind.return_value = mock_provider
            mock_provider.get.return_value = GeneralConfig(engine="v2")
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.return_value = mock_svc
                result = get_effective_engine(None)
        assert result == "v2"

    def test_config_exception_falls_back_to_v1(self) -> None:
        """Any config exception results in v1 default."""
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("boom")
                assert get_effective_engine(None) == "v1"

    def test_opaque_object_not_treated_as_string(self) -> None:
        """OptionInfo-like objects (truthy but not str) don't trigger .lower()."""
        opaque = object()
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("no config")
                result = get_effective_engine(opaque)  # type: ignore[arg-type]
        assert result == "v1"


class TestDetectCollectionEngine:
    def _write_manifest(self, root: Path, name: str, payload) -> None:
        coll = root / name
        coll.mkdir(parents=True, exist_ok=True)
        (coll / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_detects_v2_from_version_2(self, tmp_path: Path) -> None:
        self._write_manifest(
            tmp_path, "v2coll", {"name": "v2coll", "version": "2.0", "num_documents": 1}
        )
        assert detect_collection_engine("v2coll", tmp_path) == "v2"

    def test_detects_v1_when_no_version_key(self, tmp_path: Path) -> None:
        self._write_manifest(
            tmp_path,
            "v1coll",
            {
                "collectionName": "v1coll",
                "numberOfDocuments": 4,
                "numberOfChunks": 12,
                "indexers": [{"name": "FAISS"}],
            },
        )
        assert detect_collection_engine("v1coll", tmp_path) == "v1"

    def test_returns_none_for_missing_collection_dir(self, tmp_path: Path) -> None:
        assert detect_collection_engine("ghost", tmp_path) is None

    def test_returns_none_when_manifest_missing(self, tmp_path: Path) -> None:
        (tmp_path / "halfwritten").mkdir()
        assert detect_collection_engine("halfwritten", tmp_path) is None

    def test_returns_none_for_malformed_json(self, tmp_path: Path) -> None:
        coll = tmp_path / "broken"
        coll.mkdir()
        (coll / "manifest.json").write_text("{not json", encoding="utf-8")
        assert detect_collection_engine("broken", tmp_path) is None

    def test_returns_none_for_non_dict_payload(self, tmp_path: Path) -> None:
        self._write_manifest(tmp_path, "listy", ["not", "a", "dict"])
        assert detect_collection_engine("listy", tmp_path) is None

    def test_version_1_string_returns_v1(self, tmp_path: Path) -> None:
        # Forward-proof: explicit "1.x" still maps to v1.
        self._write_manifest(tmp_path, "v1explicit", {"version": "1.0"})
        assert detect_collection_engine("v1explicit", tmp_path) == "v1"

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        self._write_manifest(tmp_path, "v2coll", {"version": "2.0"})
        assert detect_collection_engine("v2coll", str(tmp_path)) == "v2"


class TestGetEffectiveEngineWithDetection:
    def _write_v2(self, root: Path, name: str) -> None:
        coll = root / name
        coll.mkdir(parents=True, exist_ok=True)
        (coll / "manifest.json").write_text(
            json.dumps({"name": name, "version": "2.0"}), encoding="utf-8"
        )

    def _write_v1(self, root: Path, name: str) -> None:
        coll = root / name
        coll.mkdir(parents=True, exist_ok=True)
        (coll / "manifest.json").write_text(
            json.dumps({"collectionName": name, "indexers": []}), encoding="utf-8"
        )

    def test_command_flag_overrides_v2_manifest(self, tmp_path: Path) -> None:
        self._write_v2(tmp_path, "coll")
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            result = get_effective_engine(
                "v1", collection="coll", collections_path=tmp_path
            )
        assert result == "v1"

    def test_v2_manifest_returns_v2_without_flag(self, tmp_path: Path) -> None:
        self._write_v2(tmp_path, "coll")
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("ignored")
                result = get_effective_engine(
                    None, collection="coll", collections_path=tmp_path
                )
        assert result == "v2"

    def test_v1_manifest_returns_v1_without_flag(self, tmp_path: Path) -> None:
        self._write_v1(tmp_path, "coll")
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("ignored")
                result = get_effective_engine(
                    None, collection="coll", collections_path=tmp_path
                )
        assert result == "v1"

    def test_missing_manifest_falls_back_to_config_default(self, tmp_path: Path) -> None:
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            mock_svc = MagicMock()
            mock_provider = MagicMock()
            mock_svc.bind.return_value = mock_provider
            mock_provider.get.return_value = GeneralConfig(engine="v2")
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.return_value = mock_svc
                result = get_effective_engine(
                    None, collection="ghost", collections_path=tmp_path
                )
        assert result == "v2"

    def test_no_collection_arg_preserves_legacy_behavior(self, tmp_path: Path) -> None:
        with patch("click.get_current_context", side_effect=RuntimeError("no ctx")):
            with patch("indexed_config.ConfigService") as mock_svc_cls:
                mock_svc_cls.instance.side_effect = Exception("no config")
                # No collection / no path → legacy path → "v1"
                assert get_effective_engine(None) == "v1"

    def test_ctx_obj_engine_takes_priority_over_manifest(self, tmp_path: Path) -> None:
        self._write_v2(tmp_path, "coll")
        mock_ctx = MagicMock()
        mock_ctx.obj = {"engine": "v1"}
        with patch("click.get_current_context", return_value=mock_ctx):
            result = get_effective_engine(
                None, collection="coll", collections_path=tmp_path
            )
        assert result == "v1"


class TestGetCollectionService:
    def test_v1_returns_module_with_create(self) -> None:
        svc = get_collection_service("v1")
        assert hasattr(svc, "create")
        assert hasattr(svc, "update")
        assert hasattr(svc, "clear")

    def test_v2_returns_module_with_create(self) -> None:
        svc = get_collection_service("v2")
        assert hasattr(svc, "create")
        assert hasattr(svc, "update")
        assert hasattr(svc, "clear")

    def test_v1_is_different_from_v2(self) -> None:
        assert get_collection_service("v1") is not get_collection_service("v2")


class TestGetSearchService:
    def test_v1_returns_module_with_search(self) -> None:
        svc = get_search_service("v1")
        assert hasattr(svc, "search")

    def test_v2_returns_module_with_search(self) -> None:
        svc = get_search_service("v2")
        assert hasattr(svc, "search")

    def test_v1_is_different_from_v2(self) -> None:
        assert get_search_service("v1") is not get_search_service("v2")


class TestGetInspectService:
    def test_v1_returns_module_with_status_and_inspect(self) -> None:
        svc = get_inspect_service("v1")
        assert hasattr(svc, "status")
        assert hasattr(svc, "inspect")

    def test_v2_returns_module_with_status_and_inspect(self) -> None:
        svc = get_inspect_service("v2")
        assert hasattr(svc, "status")
        assert hasattr(svc, "inspect")

    def test_v1_is_different_from_v2(self) -> None:
        assert get_inspect_service("v1") is not get_inspect_service("v2")
