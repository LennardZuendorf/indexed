"""Unit tests for the engine router."""

from unittest.mock import MagicMock, patch

import pytest

from indexed.services.engine_router import (
    GeneralConfig,
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
