from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .env_writer import EnvFileWriter
from .errors import ConfigValidationError
from .path_utils import get_by_path, set_by_path, delete_by_path
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
    """Singleton registry + I/O for application configuration.

    Thin orchestrator that delegates to:
    - ConfigRegistry: spec registration
    - WorkspaceManager: workspace preferences, storage paths, conflict detection
    - EnvFileWriter: sensitive field routing to .env files
    - TomlStore: raw TOML I/O
    """

    _instance: "ConfigService" | None = None

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

    # ── Singleton ────────────────────────────────────────────────────────

    @classmethod
    def instance(
        cls,
        *,
        workspace: Optional[Path] = None,
        mode_override: Optional[StorageMode] = None,
        reset: bool = False,
    ) -> "ConfigService":
        """Get or create the singleton ConfigService."""
        if cls._instance is None or reset:
            cls._instance = cls(workspace=workspace, mode_override=mode_override)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear the singleton."""
        cls._instance = None

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

        If mode_override is set, delegates to TomlStore.read() which handles
        single-mode reads. Otherwise, resolves the storage mode via
        WorkspaceManager and uses read_for_mode() to read ONE config source.
        """
        if self._mode_override:
            return self._store.read()
        mode = self._workspace.resolve_storage_mode()
        return self._store.read_for_mode(mode)

    def get_raw(self) -> Dict[str, Any]:
        """Retrieve the merged raw configuration (alias for load_raw)."""
        return self.load_raw()

    def save_raw(self, data: Dict[str, Any]) -> None:
        """Persist raw configuration to the workspace TOML store."""
        self._store.write(data)

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
                # No user config under this namespace. Try defaults; if the
                # spec has required fields, Pydantic raises and we skip.
                try:
                    instances[spec] = spec.model_validate({})  # type: ignore[arg-type]
                    path_to_type[path] = spec
                except ValidationError:
                    pass
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

    def set(self, dot_path: str, value: Any) -> None:
        """Set a value at the given dot-path and persist."""
        raw = self.load_raw()
        set_by_path(raw, dot_path, value)
        self.save_raw(raw)

    def delete(self, dot_path: str) -> bool:
        """Delete a value at a dot-path and persist if changed."""
        raw = self.load_raw()
        changed = delete_by_path(raw, dot_path)
        if changed:
            self.save_raw(raw)
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
