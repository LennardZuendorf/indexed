from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from .path_utils import get_by_path, set_by_path, delete_by_path
from .store import TomlStore
from .provider import Provider
from .storage import StorageMode, StorageResolver, get_global_root, get_resolver, reset_resolver

T = TypeVar("T", bound=BaseModel)

# Workspace preferences section in config
WORKSPACE_PREFS_PATH = "workspace_preferences"


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
        """Initialize ConfigService.
        
        Args:
            workspace: Optional workspace path. Defaults to current working directory.
            mode_override: Optional storage mode override ("global" or "local").
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
        """Get or create the singleton ConfigService instance.
        
        Args:
            workspace: Optional workspace path.
            mode_override: Optional storage mode override.
            reset: If True, create a new instance even if one exists.
            
        Returns:
            ConfigService singleton instance.
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
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
        reset_resolver()
    
    @property
    def store(self) -> TomlStore:
        """Access the underlying TomlStore."""
        return self._store
    
    @property
    def resolver(self) -> StorageResolver:
        """Access the storage resolver."""
        return self._resolver
    
    @property
    def workspace(self) -> Path:
        """Get the current workspace path."""
        return self._workspace

    # Registry
    def register(self, spec: Type[T], *, path: str) -> None:
        """Register a config spec at a dot-path.
        
        Idempotent - can be called multiple times with same spec.
        """
        self._specs[path] = spec

    # I/O
    def load_raw(self) -> Dict[str, Any]:
        """Load raw merged config (global + workspace + env)."""
        return self._store.read()
    
    def get_raw(self) -> Dict[str, Any]:
        """Alias for load_raw() for consistency."""
        return self.load_raw()

    def save_raw(self, data: Dict[str, Any]) -> None:
        """Save config to workspace TOML."""
        self._store.write(data)

    # Typed binding
    def bind(self) -> Provider:
        """Load, validate, and bind all registered specs.
        
        Returns:
            Provider with typed config instances.
            
        Raises:
            ValueError: If any registered spec fails validation.
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
        return get_by_path(self.load_raw(), dot_path)

    def set(self, dot_path: str, value: Any) -> None:
        raw = self.load_raw()
        set_by_path(raw, dot_path, value)
        self.save_raw(raw)

    def delete(self, dot_path: str) -> bool:
        raw = self.load_raw()
        changed = delete_by_path(raw, dot_path)
        if changed:
            self.save_raw(raw)
        return changed

    # Validation across all registered specs
    def validate(self) -> List[Tuple[str, str]]:
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
        """Validate requirements for a config class.
        
        Checks which required fields are present (from config, env, or cli_overrides)
        and which are missing.
        
        Args:
            config_class: Pydantic model class to validate against.
            namespace: Dot-path namespace for config lookup (e.g., 'sources.jira_cloud').
            cli_overrides: Optional dict of values provided via CLI.
            
        Returns:
            Dict with:
                - present: Dict[str, Any] - field names to their values
                - missing: List[str] - field names that are required but missing
                - field_info: Dict[str, Dict] - field names to field metadata
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
        """Determine if a field is sensitive (should be stored in env/.env)."""
        sensitive_patterns = ["token", "password", "secret", "api_key", "api_token"]
        name_lower = field_name.lower()
        return any(pattern in name_lower for pattern in sensitive_patterns)
    
    def _get_env_var_name(self, field_name: str, field: FieldInfo) -> str | None:
        """Get environment variable name for a field if applicable."""
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
        """Set a config value, routing to env/.env for sensitive fields.
        
        Args:
            dot_path: Dot-separated path (e.g., 'sources.jira.url').
            value: Value to set.
            field_info: Optional field metadata dict with 'sensitive' key.
                       Can also include 'env_var' to specify exact env var name.
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
        """Convert field name to environment variable name."""
        env_mappings = {
            "api_token": "ATLASSIAN_TOKEN",
            "token": "JIRA_TOKEN",
            "email": "ATLASSIAN_EMAIL",
            "password": "JIRA_PASSWORD",
            "login": "JIRA_LOGIN",
        }
        return env_mappings.get(field_name, field_name.upper())
    
    def _write_to_env_file(self, key: str, value: str) -> None:
        """Write a key-value pair to the .indexed/.env file."""
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
    # Workspace Preferences
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_workspace_preference(
        self,
        workspace_path: Optional[Path] = None,
    ) -> Optional[StorageMode]:
        """Get the storage mode preference for a workspace.
        
        Args:
            workspace_path: Path to the workspace. Defaults to current workspace.
            
        Returns:
            "global" or "local" if a preference exists, None otherwise.
        """
        path = str(workspace_path or self._workspace)
        
        # Read from global config directly (preferences are stored globally)
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()
        
        prefs = get_by_path(raw, WORKSPACE_PREFS_PATH, default={}) or {}
        pref = prefs.get(path)
        
        if pref in ("global", "local"):
            return pref  # type: ignore[return-value]
        return None
    
    def set_workspace_preference(
        self,
        mode: StorageMode,
        workspace_path: Optional[Path] = None,
    ) -> None:
        """Set the storage mode preference for a workspace.
        
        Preferences are stored in the global config file so they persist
        across all invocations of indexed.
        
        Args:
            mode: Storage mode ("global" or "local").
            workspace_path: Path to the workspace. Defaults to current workspace.
        """
        path = str(workspace_path or self._workspace)
        
        # Read global config, update, and write back
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()
        
        # Ensure workspace_preferences section exists
        if WORKSPACE_PREFS_PATH not in raw:
            raw[WORKSPACE_PREFS_PATH] = {}
        
        raw[WORKSPACE_PREFS_PATH][path] = mode
        global_store.write(raw, to_global=True)
    
    def clear_workspace_preference(
        self,
        workspace_path: Optional[Path] = None,
    ) -> bool:
        """Clear the storage mode preference for a workspace.
        
        Args:
            workspace_path: Path to the workspace. Defaults to current workspace.
            
        Returns:
            True if a preference was cleared, False if none existed.
        """
        path = str(workspace_path or self._workspace)
        
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()
        
        prefs = raw.get(WORKSPACE_PREFS_PATH, {})
        if path in prefs:
            del prefs[path]
            raw[WORKSPACE_PREFS_PATH] = prefs
            global_store.write(raw, to_global=True)
            return True
        return False
    
    def get_all_workspace_preferences(self) -> Dict[str, StorageMode]:
        """Get all workspace preferences.
        
        Returns:
            Dict mapping workspace paths to their storage mode preferences.
        """
        global_store = TomlStore(mode_override="global")
        raw = global_store.read()
        
        prefs = get_by_path(raw, WORKSPACE_PREFS_PATH, default={}) or {}
        return {k: v for k, v in prefs.items() if v in ("global", "local")}
    
    # ─────────────────────────────────────────────────────────────────────────
    # Storage & Conflict Detection
    # ─────────────────────────────────────────────────────────────────────────
    
    def has_config_conflict(self) -> bool:
        """Check if both local and global configs exist with differences.
        
        Returns:
            True if both configs exist and have differing values.
        """
        return self._store.configs_differ()
    
    def get_config_differences(self) -> Dict[str, tuple[Any, Any]]:
        """Get differences between local and global configs.
        
        Returns:
            Dict mapping dot-paths to (local_value, global_value) tuples.
        """
        return self._store.get_config_differences()
    
    def resolve_storage_mode(self) -> StorageMode:
        """Resolve the effective storage mode for the current workspace.
        
        Resolution order:
        1. CLI mode override (set at init)
        2. Workspace preference from config
        3. Default to "global"
        
        Returns:
            "global" or "local"
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
        """Get the resolved collections path based on current storage mode."""
        pref = self.get_workspace_preference()
        return self._resolver.get_collections_path(pref)
    
    def get_caches_path(self) -> Path:
        """Get the resolved caches path based on current storage mode."""
        pref = self.get_workspace_preference()
        return self._resolver.get_caches_path(pref)
    
    def ensure_storage_dirs(self) -> None:
        """Ensure storage directories exist for the resolved storage mode."""
        pref = self.get_workspace_preference()
        self._resolver.ensure_dirs(pref)
