from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from .path_utils import get_by_path, set_by_path, delete_by_path
from .store import TomlStore
from .provider import Provider
from .storage import StorageMode, StorageResolver, get_resolver, reset_resolver

T = TypeVar("T", bound=BaseModel)

# Workspace config section in config
WORKSPACE_PATH = "workspace"

# Default global path
DEFAULT_GLOBAL_PATH = "~/.indexed"


class ConfigService:
    """Singleton registry + I/O for application configuration.

    - register(spec, path): declare a typed slice at a dot-path
    - bind(): load+merge+validate all registered specs and return Provider
    - get/set/delete: operate on raw mapping (workspace TOML as write target)
    - validate(): validate all specs; returns list of (path, error)
    - workspace preferences: per-directory storage mode preferences
    """

    _instance: "ConfigService" | None = None

    def __init__(
        self,
        *,
        workspace: Optional[Path] = None,
        mode_override: Optional[StorageMode] = None,
    ) -> None:
        """
        Create a ConfigService bound to a specific workspace and optional storage mode override.
        
        Parameters:
            workspace (Optional[Path]): Workspace directory used for config storage; defaults to the current working directory.
            mode_override (Optional[StorageMode]): If provided, forces the storage mode ("global" or "local") for this service instance.
        """
        self._specs: Dict[str, Type[BaseModel]] = {}
        self._workspace = workspace or Path.cwd()
        self._mode_override = mode_override
        self._store = TomlStore(workspace=self._workspace, mode_override=mode_override)
        self._resolver = StorageResolver(workspace=self._workspace, mode_override=mode_override)

    @classmethod
    def instance(
        cls,
        *,
        workspace: Optional[Path] = None,
        mode_override: Optional[StorageMode] = None,
        reset: bool = False,
    ) -> "ConfigService":
        """
        Get or create the singleton ConfigService.
        
        Parameters:
            workspace (Optional[Path]): Workspace path to bind the service to when creating a new instance; defaults to the current working directory.
            mode_override (Optional[StorageMode]): Storage mode override to apply when creating a new instance.
            reset (bool): If True, force creation of a new instance even if one already exists.
        
        Returns:
            ConfigService: The singleton ConfigService instance.
        """
        if cls._instance is None or reset:
            cls._instance = cls(workspace=workspace, mode_override=mode_override)
            # Also reset the module-level resolver singleton so services use
            # the same mode_override setting
            get_resolver(
                workspace=workspace,
                mode_override=mode_override,
                reset=True,
            )
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """
        Clear the ConfigService singleton and reset the module-level storage resolver.
        
        This sets the class singleton reference to None and calls the global resolver reset function to restore resolver state.
        """
        cls._instance = None
        reset_resolver()
    
    @property
    def store(self) -> TomlStore:
        """
        Provide access to the configured TOML-backed store.
        
        Returns:
            store (TomlStore): The underlying TOML store used for configuration I/O.
        """
        return self._store
    
    @property
    def resolver(self) -> StorageResolver:
        """
        Access the storage resolver.
        
        Returns:
            resolver (StorageResolver): Resolver responsible for resolving storage modes and paths.
        """
        return self._resolver
    
    @property
    def workspace(self) -> Path:
        """
        Current workspace path.
        
        Returns:
            Path: The workspace directory used by this ConfigService instance.
        """
        return self._workspace

    # Registry
    def register(self, spec: Type[T], *, path: str) -> None:
        """
        Register a typed configuration spec under a dot-separated namespace.
        
        Registers the given Pydantic model type as the config schema for the specified dot-path. If called again for the same path, the new spec replaces the previous one (registration is idempotent with respect to the intended mapping).
        
        Parameters:
            spec (Type[T]): A Pydantic BaseModel subclass describing the config schema.
            path (str): Dot-separated path in the merged config where this spec's data will be read from and written to.
        """
        self._specs[path] = spec

    # I/O
    def load_raw(self) -> Dict[str, Any]:
        """
        Retrieve the merged raw configuration from global, workspace, and environment sources.
        
        Returns:
            raw (Dict[str, Any]): Dictionary containing the merged configuration values.
        """
        return self._store.read()
    
    def get_raw(self) -> Dict[str, Any]:
        """
        Retrieve the merged raw configuration from storage.
        
        Returns:
            dict: The merged raw configuration as a mapping of configuration keys to their values.
        """
        return self.load_raw()

    def save_raw(self, data: Dict[str, Any]) -> None:
        """
        Persist the provided raw configuration to the workspace TOML store.
        
        Parameters:
            data (Dict[str, Any]): Merged raw configuration to write to the workspace TOML.
        """
        self._store.write(data)

    # Typed binding
    def bind(self) -> Provider:
        """
        Bind registered config specs to validated model instances using the merged raw configuration.
        
        Loads the merged raw configuration, validates each registered spec present in the raw data, and returns a Provider containing the validated instances and related metadata.
        
        Returns:
            Provider: Contains three items—
                - `instances`: mapping of spec type to its validated `BaseModel` instance,
                - `raw`: the merged raw configuration dictionary,
                - `path_to_type`: mapping from dot-path string to the corresponding spec type.
        
        Raises:
            ValueError: If validation fails for any registered spec; the error message includes the spec's dot-path.
        """
        raw = self.load_raw()
        instances: Dict[type, BaseModel] = {}
        path_to_type: Dict[str, Type[BaseModel]] = {}
        
        for path, spec in self._specs.items():
            payload = get_by_path(raw, path, default=None)
            # Skip specs that are not present in config (optional sections)
            if payload in (None, {}):
                continue
            try:
                instances[spec] = spec.model_validate(payload)  # type: ignore[arg-type]
                path_to_type[path] = spec
            except ValidationError as exc:
                # Surface early by raising; caller can handle
                raise ValueError(f"Invalid config for '{path}': {exc}") from exc
        
        return Provider(instances, raw, path_to_type)

    # Raw ops with dot-paths (write to workspace TOML)
    def get(self, dot_path: str) -> Any:
        """
        Retrieve a value from the merged raw configuration using a dot-separated path.
        
        Parameters:
            dot_path (str): Dot-separated path specifying the key to retrieve from the merged configuration.
        
        Returns:
            Any: The value at the specified path, or `None` if the path does not exist.
        """
        return get_by_path(self.load_raw(), dot_path)

    def set(self, dot_path: str, value: Any) -> None:
        """
        Set a value in the merged raw configuration at the given dot-path and persist the change to the workspace TOML store.
        
        Parameters:
            dot_path (str): Dot-delimited path indicating where to set the value in the configuration (e.g., "section.sub.key").
            value (Any): The value to store at the specified path.
        """
        raw = self.load_raw()
        set_by_path(raw, dot_path, value)
        self.save_raw(raw)

    def delete(self, dot_path: str) -> bool:
        """
        Delete the value at a dot-separated path from the merged raw configuration and persist the updated config if a change occurred.
        
        Parameters:
            dot_path (str): Dot-separated path identifying the configuration key to remove.
        
        Returns:
            `true` if a value was removed and the change was saved, `false` otherwise.
        """
        raw = self.load_raw()
        changed = delete_by_path(raw, dot_path)
        if changed:
            self.save_raw(raw)
        return changed

    # Validation across all registered specs
    def validate(self) -> List[Tuple[str, str]]:
        """
        Validate all registered configuration specs against the merged raw configuration.
        
        Only sections that are present and non-empty in the merged config are validated; absent or empty optional sections are skipped. Validation failures are collected as pairs of the spec dot-path and the validation error message.
        
        Returns:
            errors (List[Tuple[str, str]]): List of tuples where the first element is the spec's dot-path and the second element is the validation error message.
        """
        raw = self.load_raw()
        errors: List[Tuple[str, str]] = []
        for path, spec in self._specs.items():
            payload = get_by_path(raw, path, default=None)
            # Only validate sections that exist (skip absent optional sections)
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
    ) -> Dict[str, Any]:
        """
        Determine which fields of a Pydantic config class are provided and which required fields are missing within the given namespace.
        
        Parameters:
            config_class (Type[BaseModel]): Pydantic model class describing the config schema.
            namespace (str): Dot-path namespace to look up config values (for example, "sources.jira").
            cli_overrides (Dict[str, Any] | None): Optional mapping of field names to values provided via CLI; these take precedence over file and environment values.
        
        Returns:
            Dict[str, Any]: A mapping with:
                - present (Dict[str, Any]): Field names to their resolved values (from CLI overrides, config file, environment for sensitive fields, or defaults).
                - missing (List[str]): Names of fields that are required by the model but have no provided value.
                - field_info (Dict[str, Dict[str, Any]]): Per-field metadata including:
                    - required (bool): Whether the field is required by the model.
                    - description (str): Field description from the model (empty string if none).
                    - default (Any | None): Field default value if defined, otherwise None.
                    - sensitive (bool): Whether the field is considered sensitive.
        """
        if cli_overrides is None:
            cli_overrides = {}
        
        raw = self.load_raw()
        config_data = get_by_path(raw, namespace, default={}) or {}
        
        present: Dict[str, Any] = {}
        missing: List[str] = []
        field_info: Dict[str, Dict[str, Any]] = {}
        
        # Get model fields from Pydantic
        model_fields = config_class.model_fields
        
        for field_name, field in model_fields.items():
            # Build field info dict
            info: Dict[str, Any] = {
                "required": field.is_required(),
                "description": field.description or "",
                "default": field.default if field.default is not None else None,
                "sensitive": self._is_sensitive_field(field_name, field),
            }
            field_info[field_name] = info
            
            # Check for value in order of precedence:
            # 1. CLI overrides
            # 2. Config file (namespace)
            # 3. Environment variable (for sensitive fields)
            value = None
            
            if field_name in cli_overrides:
                value = cli_overrides[field_name]
            elif field_name in config_data:
                value = config_data[field_name]
            else:
                # Try env var for sensitive fields
                env_var = self._get_env_var_name(field_name, field)
                if env_var:
                    value = os.getenv(env_var)
            
            if value is not None and value != "":
                present[field_name] = value
            elif field.is_required():
                missing.append(field_name)
            elif field.default is not None:
                # Has a default, so it's effectively present
                present[field_name] = field.default
        
        return {
            "present": present,
            "missing": missing,
            "field_info": field_info,
        }
    
    def _is_sensitive_field(self, field_name: str, field: FieldInfo) -> bool:
        """
        Detect whether a configuration field should be treated as sensitive.
        
        Sensitivity is determined from the field name (e.g., contains substrings like "token", "password", "secret", "api_key", or "api_token").
        
        Returns:
            True if the field name indicates sensitivity, False otherwise.
        """
        sensitive_patterns = ["token", "password", "secret", "api_key", "api_token"]
        name_lower = field_name.lower()
        return any(pattern in name_lower for pattern in sensitive_patterns)
    
    def _get_env_var_name(self, field_name: str, field: FieldInfo) -> str | None:
        """
        Determine the environment variable name associated with a config field.
        
        If the field's description contains an explicit "env: NAME" hint, that name is returned.
        Otherwise, common field-name-to-environment-variable mappings are used.
        
        Parameters:
            field_name (str): The config field's name (dot/path segment or attribute name).
            field (FieldInfo): Pydantic FieldInfo providing metadata such as description.
        
        Returns:
            The environment variable name if one can be determined, `None` otherwise.
        """
        # Check if field description mentions an env var
        desc = field.description or ""
        if "env:" in desc.lower():
            # Extract env var name from description like "API token (env: ATLASSIAN_TOKEN)"
            import re
            match = re.search(r'env:\s*(\w+)', desc, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Common env var mappings
        env_mappings = {
            "api_token": "ATLASSIAN_TOKEN",
            "token": "JIRA_TOKEN",
            "email": "ATLASSIAN_EMAIL",
            "password": "JIRA_PASSWORD",
            "login": "JIRA_LOGIN",
        }
        return env_mappings.get(field_name)

    def set_value(
        self,
        dot_path: str,
        value: Any,
        field_info: Dict[str, Any] | None = None,
    ) -> None:
        """
        Set a configuration value, writing sensitive fields to the environment file and other fields to the TOML store.
        
        Parameters:
            dot_path (str): Dot-separated configuration path (e.g., "sources.jira.url").
            value (Any): Value to store.
            field_info (dict | None): Optional metadata. If it contains `'sensitive': True`, the value is written to an environment variable. If it contains `'env_var'`, that variable name is used; otherwise an environment variable name is derived from the field name.
        """
        # Route sensitive values to .env file instead of TOML
        if field_info and field_info.get("sensitive"):
            # Check if explicit env_var is provided
            if field_info.get("env_var"):
                env_var = field_info["env_var"]
            else:
                # Get the field name from dot_path (last segment)
                field_name = dot_path.split(".")[-1]
                env_var = self._field_to_env_var(field_name)
            self._write_to_env_file(env_var, value)
        else:
            # Non-sensitive: write to TOML config
            self.set(dot_path, value)
    
    def _field_to_env_var(self, field_name: str) -> str:
        """
        Map a configuration field name to its corresponding environment variable name.
        
        Parameters:
        	field_name (str): The config field name to map.
        
        Returns:
        	env_var (str): The environment variable name for the field; uses predefined mappings for common names (e.g., "api_token" -> "ATLASSIAN_TOKEN") and otherwise returns the uppercase form of the field name.
        """
        env_mappings = {
            "api_token": "ATLASSIAN_TOKEN",
            "token": "JIRA_TOKEN",
            "email": "ATLASSIAN_EMAIL",
            "password": "JIRA_PASSWORD",
            "login": "JIRA_LOGIN",
        }
        return env_mappings.get(field_name, field_name.upper())
    
    def _write_to_env_file(self, key: str, value: str) -> None:
        """
        Write or update an environment variable in the workspace .indexed/.env file.
        
        Reads the existing .env if present and replaces the line for `key` with `key=value`; if `key` is not found, appends `key=value`. Ensures the parent directory exists before writing the updated file.
        
        Parameters:
            key (str): Environment variable name to set.
            value (str): Value to assign to the environment variable.
        """
        env_path = self._store.get_env_path()
        
        # Read existing .env content
        existing_lines: List[str] = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                existing_lines = f.readlines()
        
        # Update or add the key
        key_found = False
        updated_lines: List[str] = []
        for line in existing_lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                updated_lines.append(f"{key}={value}\n")
                key_found = True
            else:
                updated_lines.append(line if line.endswith("\n") else line + "\n")
        
        if not key_found:
            updated_lines.append(f"{key}={value}\n")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
        
        # Write back
        with open(env_path, "w") as f:
            f.writelines(updated_lines)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Workspace Configuration
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_workspace_preference(
        self,
        workspace_path: Optional[Path] = None,
    ) -> Optional[StorageMode]:
        """
        Retrieve the storage mode preference for a workspace.
        
        Parameters:
            workspace_path (Path | None): Path to the workspace; if None, uses the service's current workspace.
        
        Returns:
            str | None: `"global"` or `"local"` if a preference is configured for the workspace, `None` otherwise.
        """
        # Read from global config directly (workspace config is stored globally)
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()
        
        workspace_config = get_by_path(raw, WORKSPACE_PATH, default={}) or {}
        mode = workspace_config.get("mode")
        
        if mode in ("global", "local"):
            return mode  # type: ignore[return-value]
        return None
    
    def set_workspace_preference(
        self,
        mode: StorageMode,
        workspace_path: Optional[Path] = None,
        global_path: Optional[str] = None,
    ) -> None:
        """
        Persist the workspace's storage preference into the global configuration.
        
        Stores a small workspace config record in the global TOML store so the chosen storage
        mode and paths persist across runs.
        
        Parameters:
            mode (StorageMode): Storage mode to persist ("global" or "local").
            workspace_path (Optional[Path]): Workspace path to record; defaults to this service's workspace.
            global_path (Optional[str]): Global storage path to record; omitted if equal to the default.
        """
        local_path = str(workspace_path or self._workspace)
        
        # Read global config, update, and write back
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()
        
        # Build workspace config
        workspace_config: Dict[str, str] = {
            "mode": mode,
            "local_path": local_path,
        }
        
        # Only include global_path if non-default
        if global_path and global_path != DEFAULT_GLOBAL_PATH:
            workspace_config["global_path"] = global_path
        
        raw[WORKSPACE_PATH] = workspace_config
        global_store.write(raw, to_global=True)
    
    def clear_workspace_preference(
        self,
        workspace_path: Optional[Path] = None,
    ) -> bool:
        """
        Clear any stored workspace preference from the global configuration.
        
        Parameters:
            workspace_path (Optional[Path]): Ignored; present for API compatibility.
        
        Returns:
            bool: `True` if the workspace preference existed and was removed, `False` otherwise.
        """
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()
        
        if WORKSPACE_PATH in raw:
            del raw[WORKSPACE_PATH]
            global_store.write(raw, to_global=True)
            return True
        return False
    
    def get_workspace_config(self) -> Dict[str, str]:
        """
        Retrieve the effective workspace configuration merged from global and workspace sources.
        
        Returns:
            dict: Mapping with keys:
                - `mode` (str): Either "global" or "local".
                - `local_path` (str): Path to the workspace-local config (defaults to the service workspace).
                - `global_path` (str): Path to the global config (defaults to DEFAULT_GLOBAL_PATH).
            Returns an empty dict if no valid workspace configuration exists.
        """
        # Read from merged config (local + global)
        raw = self.load_raw()
        
        workspace_config = get_by_path(raw, WORKSPACE_PATH, default={}) or {}
        
        # Validate and return only valid config
        if workspace_config.get("mode") not in ("global", "local"):
            return {}
        
        return {
            "mode": workspace_config.get("mode", ""),
            "local_path": workspace_config.get("local_path", str(self._workspace)),
            "global_path": workspace_config.get("global_path", DEFAULT_GLOBAL_PATH),
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # Storage & Conflict Detection
    # ─────────────────────────────────────────────────────────────────────────
    
    def has_config_conflict(self) -> bool:
        """
        Determine whether both workspace-local and global configuration files exist and contain different values.
        
        Returns:
            `true` if both local and global configs exist and have differing values, `false` otherwise.
        """
        return self._store.configs_differ()
    
    def get_config_differences(self) -> Dict[str, tuple[Any, Any]]:
        """Get differences between local and global configs.
        
        Returns:
            Dict mapping dot-paths to (local_value, global_value) tuples.
        """
        return self._store.get_config_differences()
    
    def resolve_storage_mode(self) -> StorageMode:
        """
        Determine the effective storage mode for the current workspace.
        
        Resolution order (highest to lowest precedence):
        1. CLI `mode_override` provided at initialization
        2. Workspace preference stored in global config
        3. Default `"global"`
        
        Returns:
            StorageMode: `"global"` or `"local"` indicating the resolved storage mode.
        """
        # CLI override takes precedence
        if self._mode_override:
            return self._mode_override
        
        # Check workspace preference
        pref = self.get_workspace_preference()
        if pref:
            return pref
        
        # Default to global
        return "global"
    
    def get_collections_path(self) -> Path:
        """
        Return the collections directory path for the resolved storage mode.
        
        Returns:
            Path: Filesystem path to the collections directory for the active storage mode.
        """
        pref = self.get_workspace_preference()
        return self._resolver.get_collections_path(pref)
    
    def get_caches_path(self) -> Path:
        """
        Resolve the caches directory path for the current workspace storage mode.
        
        Returns:
            Path: Filesystem path to the caches directory for the resolved storage mode.
        """
        pref = self.get_workspace_preference()
        return self._resolver.get_caches_path(pref)
    
    def ensure_storage_dirs(self) -> None:
        """Ensure storage directories exist for the resolved storage mode."""
        pref = self.get_workspace_preference()
        self._resolver.ensure_dirs(pref)