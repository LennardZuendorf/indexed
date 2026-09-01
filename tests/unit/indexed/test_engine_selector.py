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
    svc = MagicMock()
    svc.get.return_value = engine_value
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
    # A config service with no [core] engine set: raw get() returns None.
    svc = MagicMock()
    svc.get.return_value = None

    assert resolve_engine_selector(None, svc) == "1"


def test_core_engine_config_rejects_bad_value() -> None:
    from pydantic import ValidationError

    from indexed.core.v1.config_models import CoreEngineConfig

    with pytest.raises(ValidationError):
        CoreEngineConfig(engine="9")


# --- C2 regression: CoreEngineConfig must normalize the friendly v1/v2 forms,
# not just accept the bare "1"/"2" — env (INDEXED__CORE__ENGINE=v2) and
# `config set core.engine v2` go through this validator directly. ------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [("1", "1"), ("2", "2"), ("v1", "1"), ("v2", "2"), ("V2", "2")],
)
def test_engine_selector_normalizes(raw: str, expected: str) -> None:
    from indexed.core.v1.config_models import CoreEngineConfig

    assert CoreEngineConfig(engine=raw).engine == expected


@pytest.mark.unit
def test_engine_selector_rejects_garbage() -> None:
    from indexed.core.v1.config_models import CoreEngineConfig

    with pytest.raises(ValueError, match="v1"):
        CoreEngineConfig(engine="v3")


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


def test_bad_core_engine_in_config_matches_flag_env_message(
    monkeypatch, tmp_path: Path
) -> None:
    """R6: a hand-edited ``config.toml`` with a bad ``[core] engine`` must raise
    the exact same single-line message the ``--engine``/env paths produce — not
    a raw multi-line ``ConfigValidationError`` dump routed through pydantic."""
    from indexed.config.errors import ConfigurationError
    from indexed.config.service import ConfigService
    from indexed.cli.composition import register_app_config, resolve_engine_selector

    monkeypatch.delenv(ENV_VAR, raising=False)

    local_config = tmp_path / ".indexed" / "config.toml"
    local_config.parent.mkdir(parents=True, exist_ok=True)
    local_config.write_text('[core]\nengine = "v3"\n', encoding="utf-8")

    svc = ConfigService(workspace=tmp_path, mode_override="local")
    register_app_config(svc)

    with pytest.raises(ConfigurationError) as exc_info:
        resolve_engine_selector(None, svc)

    assert str(exc_info.value) == "Invalid engine 'v3'; expected one of: 1, 2, v1, v2"


def test_config_toml_no_core_section_falls_back_to_default(
    monkeypatch, tmp_path: Path
) -> None:
    """R6: an absent ``[core]`` section (or unset ``engine`` key) still falls
    back to the built-in default ``"1"``, unchanged from today — the raw
    ``ConfigService.get`` read must not treat "absent" as an error."""
    from indexed.config.service import ConfigService
    from indexed.cli.composition import register_app_config, resolve_engine_selector

    monkeypatch.delenv(ENV_VAR, raising=False)

    local_config = tmp_path / ".indexed" / "config.toml"
    local_config.parent.mkdir(parents=True, exist_ok=True)
    local_config.write_text("[core.v1.search]\nmax_docs = 5\n", encoding="utf-8")

    svc = ConfigService(workspace=tmp_path, mode_override="local")
    register_app_config(svc)

    assert resolve_engine_selector(None, svc) == "1"


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
