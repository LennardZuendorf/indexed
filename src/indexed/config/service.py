from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .env_writer import EnvFileWriter
from .errors import ConfigValidationError
from .path_utils import get_by_path, set_by_path, delete_by_path, deep_merge
from .registry import ConfigRegistry
from .store import TomlStore
from .provider import Provider
from .storage import StorageMode, StorageResolver
from .workspace import WorkspaceManager

T = TypeVar("T", bound=BaseModel)


class ValidationResult(BaseModel):
    """Typed result from validate_requirements()."""

    present: Dict[str, Any]
    missing: List[str]
    field_info: Dict[str, Dict[str, Any]]


class ConfigService:
    """Registry + I/O for application configuration.

    Thin orchestrator that delegates to:
    - ConfigRegistry: spec registration
    - WorkspaceManager: workspace preferences, storage paths, conflict detection
    - EnvFileWriter: sensitive field routing to .env files
    - TomlStore: raw TOML I/O

    Access the process-wide cached instance via the module-level
    ``get_config()``; clear it with ``reload()``.
    """

    def __init__(
        self,
        *,
        workspace: Optional[Path] = None,
        mode_override: Optional[StorageMode] = None,
    ) -> None:
        self._workspace_path = workspace or Path.cwd()
        self._mode_override = mode_override
        self._store = TomlStore(
            workspace=self._workspace_path, mode_override=mode_override
        )
        self._resolver = StorageResolver(
            workspace=self._workspace_path, mode_override=mode_override
        )
        self._registry = ConfigRegistry()
        self._workspace = WorkspaceManager(
            self._store, self._resolver, self._workspace_path, mode_override
        )
        self._env_writer = EnvFileWriter(self._resolved_env_path)
        # In-memory-only overrides (R3): merged on top of load_raw() but never
        # written to disk. Lets create/update pass CLI overrides & prompted
        # values through to from_config() reads without persisting them
        # (foundation/6b, bug E4). Cleared per runtime flow via clear_overlay().
        self._overlay: Dict[str, Any] = {}

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def store(self) -> TomlStore:
        """The underlying TOML store."""
        return self._store

    @property
    def resolver(self) -> StorageResolver:
        """The storage resolver."""
        return self._resolver

    @property
    def workspace(self) -> Path:
        """Current workspace path."""
        return self._workspace_path

    @property
    def workspace_manager(self) -> WorkspaceManager:
        """The workspace manager."""
        return self._workspace

    # ── Registry (delegates to ConfigRegistry) ───────────────────────────

    def register(self, spec: Type[T], *, path: str) -> None:
        """Register a typed configuration spec under a dot-separated namespace."""
        self._registry.register(spec, path=path)

    # ── I/O ──────────────────────────────────────────────────────────────

    def _resolved_env_path(self) -> str:
        """Return the .env path for the resolved storage mode.

        Used as the callable for EnvFileWriter so it always writes
        to the correct .env based on the effective storage mode.
        """
        mode = self._workspace.resolve_storage_mode()
        return self._store.get_resolved_env_path(mode)

    def load_raw(self) -> Dict[str, Any]:
        """Retrieve the raw configuration for the effective storage mode.

        Resolves the storage mode (CLI override or WorkspaceManager) and reads
        exactly one config.toml via read_for_mode().
        """
        mode = (
            self._mode_override
            if self._mode_override
            else self._workspace.resolve_storage_mode()
        )
        raw = self._store.read_for_mode(mode)
        if self._overlay:
            raw = deep_merge(raw, self._overlay)
        return raw

    def save_raw(
        self, data: Dict[str, Any], mode: Optional[StorageMode] = None
    ) -> None:
        """Persist raw configuration to the workspace TOML store.

        Args:
            mode: An already-resolved storage mode to write to verbatim. Pass
                the same mode used for the corresponding baseline read (see
                ``set()``/``delete()``) so the read and write targets can
                never diverge (R1). Omit to fall back to ``TomlStore``'s own
                resolution (used by callers with no baseline read to match).
        """
        self._store.write(data, mode=mode)

    # ── Typed binding ────────────────────────────────────────────────────

    def bind(self) -> Provider:
        """Bind registered specs to validated model instances.

        Returns:
            Provider with validated instances, raw config, and path-to-type mapping.

        Raises:
            ConfigValidationError: If validation fails for any registered spec.
        """
        raw = self.load_raw()
        # Strip internal schema version marker before validation
        raw.pop("_schema_version", None)
        instances: Dict[type, BaseModel] = {}
        path_to_type: Dict[str, Type[BaseModel]] = {}

        for path, spec in self._registry.specs.items():
            payload = get_by_path(raw, path, default=None)
            if payload in (None, {}):
                continue
            try:
                instances[spec] = spec.model_validate(payload)  # type: ignore[arg-type]
                path_to_type[path] = spec
            except ValidationError as exc:
                raise ConfigValidationError(path, str(exc)) from exc

        return Provider(instances, raw, path_to_type)

    # ── Raw ops with dot-paths ───────────────────────────────────────────

    def get(self, dot_path: str) -> Any:
        """Retrieve a value from merged config using a dot-separated path."""
        return get_by_path(self.load_raw(), dot_path)

    def _resolve_persist_mode(self) -> StorageMode:
        """Resolve the storage mode once for a set()/delete() cycle.

        Both the baseline read and the write must target the exact same
        file. Resolving the mode a single time here and threading it through
        to ``_disk_baseline()`` and ``save_raw()`` guarantees that — even
        after a correct write-side resolver fix, calling the cascade twice
        independently would still leave a seam if the stored preference
        changed on disk between the two calls (R1).
        """
        return (
            self._mode_override
            if self._mode_override
            else self._workspace.resolve_storage_mode()
        )

    def _disk_baseline(self, mode: Optional[StorageMode] = None) -> Dict[str, Any]:
        """Return the on-disk config for the resolved mode, no env overlay.

        set()/delete() persist THIS baseline plus their single change — never
        the env-merged view from load_raw() — so an INDEXED__*-supplied value
        (e.g. a secret provided only via env) is never baked into config.toml
        by an unrelated write (C2).

        Args:
            mode: An already-resolved storage mode. Omit to resolve it here
                (used by callers that don't need to thread it elsewhere).
        """
        if mode is None:
            mode = self._resolve_persist_mode()
        return self._store.read_disk_only_for_mode(mode)

    def set(self, dot_path: str, value: Any) -> None:
        """Set a value at the given dot-path and persist."""
        mode = self._resolve_persist_mode()
        raw = self._disk_baseline(mode)
        set_by_path(raw, dot_path, value)
        self.save_raw(raw, mode)

    def delete(self, dot_path: str) -> bool:
        """Delete a value at a dot-path and persist if changed."""
        mode = self._resolve_persist_mode()
        raw = self._disk_baseline(mode)
        changed = delete_by_path(raw, dot_path)
        if changed:
            self.save_raw(raw, mode)
        return changed

    # ── Validation ───────────────────────────────────────────────────────

    def validate(self) -> List[Tuple[str, str]]:
        """Validate all registered specs against merged config."""
        raw = self.load_raw()
        raw.pop("_schema_version", None)
        errors: List[Tuple[str, str]] = []
        for path, spec in self._registry.specs.items():
            payload = get_by_path(raw, path, default=None)
            if payload in (None, {}):
                continue
            try:
                spec.model_validate(payload)  # type: ignore[arg-type]
            except ValidationError as exc:
                errors.append((path, str(exc)))
        return errors

    def validate_requirements(
        self,
        config_class: Type[BaseModel],
        namespace: str,
        cli_overrides: Dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Determine which fields are provided and which required fields are missing."""
        if cli_overrides is None:
            cli_overrides = {}

        raw = self.load_raw()
        config_data = get_by_path(raw, namespace, default={}) or {}

        present: Dict[str, Any] = {}
        missing: List[str] = []
        field_info: Dict[str, Dict[str, Any]] = {}

        model_fields = config_class.model_fields

        for field_name, field in model_fields.items():
            info: Dict[str, Any] = {
                "required": field.is_required(),
                "description": field.description or "",
                "default": field.default if field.default is not None else None,
                "sensitive": EnvFileWriter.is_sensitive_field(field_name),
            }
            field_info[field_name] = info

            value = None

            if field_name in cli_overrides:
                value = cli_overrides[field_name]
            elif field_name in config_data:
                value = config_data[field_name]
            else:
                env_var = EnvFileWriter.get_env_var_name(field_name, field)
                if env_var:
                    value = os.getenv(env_var)

            if value is not None and value != "":
                present[field_name] = value
            elif field.is_required():
                missing.append(field_name)
            elif field.default is not None:
                present[field_name] = field.default

        return ValidationResult(
            present=present,
            missing=missing,
            field_info=field_info,
        )

    # ── Sensitive value routing (delegates to EnvFileWriter) ─────────────

    def set_value(
        self,
        dot_path: str,
        value: Any,
        field_info: Dict[str, Any] | None = None,
    ) -> None:
        """Set a config value, routing sensitive fields to .env."""
        if field_info and field_info.get("sensitive"):
            if field_info.get("env_var"):
                env_var = field_info["env_var"]
            else:
                field_name = dot_path.split(".")[-1]
                env_var = field_name.upper()
            self._env_writer.write(env_var, value)
        else:
            self.set(dot_path, value)

    def set_overlay(self, dot_path: str, value: Any) -> None:
        """Apply an in-memory-only override — never persisted to config.toml.

        ``load_raw()`` (and therefore ``get()``/``bind()``/``validate()``)
        merges this overlay on top of the on-disk + env config, so
        ``from_config()`` reads see it, but ``set()``/``save_raw()`` never
        do — a failed ``create`` (or a value only meant for this run) leaves
        no trace on disk (R3; foundation/6b bug E4).
        """
        set_by_path(self._overlay, dot_path, value)

    def clear_overlay(self) -> None:
        """Clear all in-memory overrides — call at the start of a new runtime flow."""
        self._overlay = {}

    def resolve_sensitive_env_var(self, dot_path: str) -> Optional[str]:
        """Resolve the connector-declared `.env` key for a sensitive dot-path.

        Mirrors the per-field registry lookup ``validate_requirements()`` does
        for a known ``(config_class, namespace)`` pair, but for an arbitrary
        dot-path: splits it into ``(namespace, field_name)``, finds the spec
        registered at that namespace, and reads the field's ``"env: NAME"``
        hint via ``EnvFileWriter.get_env_var_name()``.

        Returns ``None`` when no registered spec/field matches (e.g. an
        unregistered namespace, or a field the active spec doesn't declare) —
        callers should warn and fall back rather than silently writing the
        secret to a key no connector reads (C1 follow-up).
        """
        if "." not in dot_path:
            return None
        namespace, field_name = dot_path.rsplit(".", 1)
        spec = self._registry.specs.get(namespace)
        if spec is None:
            return None
        field = spec.model_fields.get(field_name)
        if field is None:
            return None
        return EnvFileWriter.get_env_var_name(field_name, field)

    # ── Workspace delegation ─────────────────────────────────────────────

    def get_workspace_preference(self) -> Optional[StorageMode]:
        """Retrieve the storage mode preference for a workspace."""
        return self._workspace.get_preference()

    def get_workspace_config(self) -> Dict[str, str]:
        """Retrieve the effective workspace configuration."""
        return self._workspace.get_config()

    # ── Storage mode resolution (delegates to WorkspaceManager) ─────────

    def resolve_storage_mode(self) -> StorageMode:
        """Determine the effective storage mode for the current workspace."""
        return self._workspace.resolve_storage_mode()


# ── Cached accessor ──────────────────────────────────────────────────────

_config_singleton: Optional[ConfigService] = None


def get_config(
    *,
    workspace: Optional[Path] = None,
    mode_override: Optional[StorageMode] = None,
) -> ConfigService:
    """Return the process-wide cached ConfigService, creating it on first use.

    Rebuilds the cached instance when ``mode_override`` is supplied and differs
    from the cached one (so switching between global/local at runtime yields a
    correctly-scoped service). Call ``reload()`` to force a fresh instance.
    """
    global _config_singleton
    if _config_singleton is None or (
        mode_override is not None and _config_singleton._mode_override != mode_override
    ):
        _config_singleton = ConfigService(
            workspace=workspace, mode_override=mode_override
        )
    return _config_singleton


def reload() -> None:
    """Clear the cached ConfigService so the next ``get_config()`` rebuilds it."""
    global _config_singleton
    _config_singleton = None
