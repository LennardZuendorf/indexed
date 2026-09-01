"""Shared, schema-driven handler for the ``create`` subcommands.

The four subcommands (``create files|jira|confluence|outline``) live in
``_create_commands.py`` as thin shells; each maps its own CLI options into
``cli_overrides`` and delegates to :func:`_create` here. Everything that differs
between sources is data in ``_create_schema.SOURCE_SPECS``.

This module owns the interactive-prompt seams the create tests patch
(``console``/``print_error``/``is_credential_field``/…): the handler resolves them
from this module's namespace, so patching ``create.<name>`` keeps working. The
command shells and their typer ``app`` are re-exported lazily via ``__getattr__``
to keep this module (and patching) circular-import free.
"""

from functools import partial
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from indexed.core.engine import SourceConfig  # noqa: F401

import typer
from loguru import logger

# Imported at module level so the create tests can patch these seams.
from indexed.config import ConfigService, ValidationResult, get_config

from ...utils.logging import is_verbose_mode
from ...utils.console import console
from ...utils.components.theme import get_heading_style, get_accent_style
from ...utils.components import print_error
from ...utils.credentials import (
    prompt_credential_field,
    is_credential_field,
    check_server_auth_present,
)
from ._create_helpers import execute_create_command

# Re-exported for tests + characterization (`from ...create import _is_cloud`).
from ._create_schema import _is_cloud as _is_cloud  # noqa: F401
from ._create_schema import (
    SOURCE_SPECS,
    SourceSpec,
    _is_pre_setup_verbose,
    make_build_source_config,
    resolve_source,
)

_LAZY_COMMANDS = {
    "app",
    "create_files",
    "create_jira",
    "create_confluence",
    "create_outline",
}


def _config_header(display_name: str) -> None:
    console.print()
    console.print(
        f"[{get_heading_style()}]{display_name} Configuration[/{get_heading_style()}]"
    )
    console.print()


def _display_storage_indicator(verbose: bool, log_level: Optional[str]) -> None:
    """Print the storage-mode indicator unless verbose/debug output is active."""
    if not _is_pre_setup_verbose(verbose, log_level):
        from ...utils.storage_info import display_storage_mode_for_command

        display_storage_mode_for_command(console)


def _resolve_url(
    spec: SourceSpec,
    url_arg: Optional[str],
    config: ConfigService,
    verbose: bool,
    log_level: Optional[str],
) -> Tuple[str, bool]:
    """Resolve the source URL, prompting when unknown.

    Atlassian sources reject an empty prompt (they need a real host to detect
    Cloud vs Server); Outline defaults to Cloud on Enter. Returns
    ``(resolved_url, url_was_prompted)``.
    """
    resolved = url_arg or config.get(f"{spec.namespace}.url")
    prompted = False
    if not resolved:
        if not _is_pre_setup_verbose(verbose, log_level):
            _config_header(spec.display_name)
        if is_verbose_mode():
            logger.info("URL not known, prompting user...")

        default = spec.url_default_fn() if spec.url_default_fn else None
        suffix = f" [{default}]" if default else ""
        raw = console.input(
            f"[{get_accent_style()}]{spec.url_label}[/{get_accent_style()}]{suffix}: "
        )
        prompted = True
        if default is not None:
            resolved = raw.strip() or default
        else:
            resolved = raw
            if not resolved:
                print_error(f"{spec.display_name} URL is required")
                raise typer.Exit(1)
    return resolved, prompted


def _prompt_missing_fields(
    spec: SourceSpec,
    source_type: str,
    header_shown: bool,
    validation: ValidationResult,
    config: ConfigService,
    namespace: str,
) -> None:
    """Prompt for the connector's missing fields, driven by the source spec.

    Credential fields route through ``prompt_credential_field`` (secrets → .env);
    everything else uses the field's prompt/parse spec and lands in the in-memory
    overlay only — never persisted to config.toml (R3; foundation/6b bug E4).
    """
    missing = [f for f in validation.missing if f not in spec.url_excludes]

    # Confluence Server/DC: auth fields are optional in the schema but the
    # connector needs at least one method, so prompt for a token when none found.
    if spec.server_auth and source_type == spec.server_source_type:
        token_env, login_env, password_env = spec.server_env
        if not check_server_auth_present(
            validation.present,
            token_env_var=token_env,
            login_env_var=login_env,
            password_env_var=password_env,
        ):
            if "token" not in missing:
                missing.append("token")
            if is_verbose_mode():
                logger.info("No auth credentials found, will prompt for token")

    if not missing:
        return

    if not header_shown and not is_verbose_mode():
        _config_header(spec.display_name)

    for name in missing:
        field_info = validation.field_info.get(name, {})
        if is_verbose_mode():
            logger.info("Prompting for missing field: %s", name)

        if is_credential_field(name):
            value: Any = prompt_credential_field(
                name, field_info, config, namespace, source_type
            )
        else:
            fs = spec.fields_by_name.get(name)
            if fs is not None:
                raw = console.input(
                    f"[{get_accent_style()}]{fs.label}[/{get_accent_style()}]{fs.suffix}: "
                )
                try:
                    value = fs.parse(raw)
                except ValueError:
                    print_error(fs.error)
                    raise typer.Exit(1)
            else:
                value = console.input(
                    f"[{get_accent_style()}]{name}[/{get_accent_style()}]: "
                )
            config.set_overlay(f"{namespace}.{name}", value)

        validation.present[name] = value
        if is_verbose_mode():
            logger.info(
                "Saved %s to %s",
                name,
                "env" if is_credential_field(name) else "in-memory overlay",
            )


def _create(
    spec_key: str,
    *,
    collection: str,
    url: Optional[str],
    cli_overrides: Dict[str, Any],
    use_cache: bool,
    force: bool,
    verbose: bool,
    json_logs: bool,
    log_level: Optional[str],
    local: bool,
    engine: Optional[str],
) -> None:
    """Resolve source type + URL from the spec, then run the shared create flow."""
    spec = SOURCE_SPECS[spec_key]

    # Storage indicator prints once here, before any connector header/prompt
    # (critical-bugs/4); execute_create_command no longer prints it.
    config = get_config(mode_override="local" if local else None)
    _display_storage_indicator(verbose, log_level)

    resolved_url: Optional[str] = None
    url_was_prompted = False
    if spec.has_url:
        resolved_url, url_was_prompted = _resolve_url(
            spec, url, config, verbose, log_level
        )
        cli_overrides = {**cli_overrides, "url": resolved_url}

    source_type, config_class = resolve_source(spec, resolved_url)

    execute_create_command(
        collection=collection,
        source_type=source_type,
        config_class=config_class,
        namespace=spec.namespace,
        cli_overrides=cli_overrides,
        prompt_missing_fields=partial(
            _prompt_missing_fields, spec, source_type, url_was_prompted
        ),
        build_source_config=make_build_source_config(spec, source_type),
        success_message_suffix=spec.success_suffix,
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        use_cache=use_cache,
        force=force,
        progress_message=(
            f"Connecting to {resolved_url}" if spec.progress_uses_url else None
        ),
        verbose_pre_creation_log=spec.verbose_log,
        pre_creation_display=spec.pre_display,
        local=local,
        source_path_key=spec.source_path_key,
        engine=engine,
    )


def __getattr__(name: str) -> Any:
    """Lazily resolve the command shells/app and the core-facade test seams.

    The shells and their typer ``app`` live in ``_create_commands`` (they use no
    patched seams); resolving them here keeps this module import-cycle free while
    preserving ``from create import create_files`` / ``create.app``.
    """
    if name in _LAZY_COMMANDS:
        from . import _create_commands

        return getattr(_create_commands, name)
    if name == "DEFAULT_INDEXER":
        from indexed.core.v1.constants import DEFAULT_INDEXER

        return DEFAULT_INDEXER
    if name == "SourceConfig":
        from indexed.core.engine import SourceConfig

        return SourceConfig
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
