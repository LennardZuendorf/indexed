"""Unit tests for the engine selector chain and ``[core] engine`` registration.

Covers plan.md scenario 2 (selector precedence: flag > env > ``[core] engine``
config > default "1") and the OQ-T1 probe (a scalar model registered at config
path ``core`` coexists with ``core.v1.*``/``core.v2.*`` subtables).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

ENV_VAR = "INDEXED__CORE__ENGINE"


def _config_service_with_engine(engine_value: str) -> MagicMock:
    from indexed.core.v1.config_models import CoreEngineConfig

    svc = MagicMock()
    svc.bind.return_value.get.return_value = CoreEngineConfig(engine=engine_value)
    return svc


def test_flag_wins_over_env_and_config(monkeypatch) -> None:
    from indexed.cli.composition import resolve_engine_selector

    monkeypatch.setenv(ENV_VAR, "1")
    svc = _config_service_with_engine("1")

    assert resolve_engine_selector("2", svc) == "2"


def test_flag_accepts_v2_alias(monkeypatch) -> None:
    from indexed.cli.composition import resolve_engine_selector

    monkeypatch.delenv(ENV_VAR, raising=False)
    svc = _config_service_with_engine("1")

    assert resolve_engine_selector("v2", svc) == "2"
    assert resolve_engine_selector("v1", svc) == "1"


def test_env_wins_over_config(monkeypatch) -> None:
    from indexed.cli.composition import resolve_engine_selector

    monkeypatch.setenv(ENV_VAR, "2")
    svc = _config_service_with_engine("1")

    assert resolve_engine_selector(None, svc) == "2"


def test_config_wins_over_default(monkeypatch) -> None:
    from indexed.cli.composition import resolve_engine_selector

    monkeypatch.delenv(ENV_VAR, raising=False)
    svc = _config_service_with_engine("2")

    assert resolve_engine_selector(None, svc) == "2"


def test_default_is_one(monkeypatch) -> None:
    from indexed.cli.composition import resolve_engine_selector

    monkeypatch.delenv(ENV_VAR, raising=False)
    # A config service that has no [core] engine registered: bind().get raises.
    svc = MagicMock()
    svc.bind.return_value.get.side_effect = KeyError("not registered")

    assert resolve_engine_selector(None, svc) == "1"


def test_core_engine_config_rejects_bad_value() -> None:
    from pydantic import ValidationError

    from indexed.core.v1.config_models import CoreEngineConfig

    with pytest.raises(ValidationError):
        CoreEngineConfig(engine="9")


def test_bad_core_engine_in_config_fails_loud(monkeypatch, tmp_path: Path) -> None:
    """A malformed ``[core] engine`` value must surface as a config error, not be
    silently downgraded to the default ``"1"`` — consistent with the env path
    (which fails loud via ``normalize_engine_selector``)."""
    from indexed.config.errors import ConfigurationError
    from indexed.config.service import ConfigService
    from indexed.cli.composition import register_app_config, resolve_engine_selector

    monkeypatch.delenv(ENV_VAR, raising=False)

    local_config = tmp_path / ".indexed" / "config.toml"
    local_config.parent.mkdir(parents=True, exist_ok=True)
    local_config.write_text('[core]\nengine = "9"\n', encoding="utf-8")

    svc = ConfigService(workspace=tmp_path, mode_override="local")
    register_app_config(svc)

    with pytest.raises(ConfigurationError):
        resolve_engine_selector(None, svc)


# --- OQ-T1 probe: real ConfigService with core + core.v1.* + core.v2.* --------


def test_core_engine_registration_coexists_with_v1_v2(tmp_path: Path) -> None:
    """Registering a scalar model at path ``core`` alongside ``core.v1.*`` /
    ``core.v2.*`` subtables binds cleanly and reads ``engine`` (extra='ignore')."""
    from pydantic import BaseModel

    from indexed.config.service import ConfigService
    from indexed.cli.composition import register_app_config
    from indexed.core.v1.config_models import CoreEngineConfig

    workspace = tmp_path
    local_config = workspace / ".indexed" / "config.toml"
    local_config.parent.mkdir(parents=True, exist_ok=True)
    local_config.write_text(
        "\n".join(
            [
                "[core]",
                'engine = "2"',
                "",
                "[core.v1.search]",
                "max_docs = 5",
                "",
                "[core.v2.embedding]",
                'model_name = "some-model"',
            ]
        ),
        encoding="utf-8",
    )

    class _FakeCoreV2Embedding(BaseModel):
        model_name: str = "default"

    svc = ConfigService(workspace=workspace, mode_override="local")
    register_app_config(svc)
    svc.register(_FakeCoreV2Embedding, path="core.v2.embedding")

    provider = svc.bind()

    assert provider.get(CoreEngineConfig).engine == "2"
    assert provider.get(_FakeCoreV2Embedding).model_name == "some-model"
