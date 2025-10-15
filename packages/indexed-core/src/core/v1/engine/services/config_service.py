"""Configuration service providing CRUD operations and profile management.

Singleton service for managing application configuration with caching,
profile support, and runtime override handling.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
from enum import Enum, auto

from core.v1.config.settings import IndexedSettings
from core.v1.config.store import (
    read_toml,
    atomic_write_toml,
    get_config_path,
    validate_no_secrets,
    ensure_indexed_toml_exists,
    ensure_env_example,
)


class ConfigService:
    """Singleton service for configuration management."""

    _instance: Optional["ConfigService"] = None
    _settings_cache: Optional[IndexedSettings] = None

    def __init__(self) -> None:
        if ConfigService._instance is not None:
            raise RuntimeError("ConfigService is a singleton. Use get_instance().")

    @classmethod
    def get_instance(cls) -> "ConfigService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _invalidate_cache(self) -> None:
        ConfigService._settings_cache = None

    def _deep_merge(
        self, base: Dict[str, Any], overlay: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = base.copy()
        for key, value in overlay.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _delete_nested_value(self, data: Dict[str, Any], key_path: str) -> bool:
        keys = key_path.split(".")
        current: Any = data
        try:
            for key in keys[:-1]:
                current = current[key]
            if keys[-1] in current:
                del current[keys[-1]]
                return True
            return False
        except (KeyError, TypeError):
            return False

    def _filter_known_top_level(self, data: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "paths",
            "search",
            "index",
            "sources",
            "mcp",
            "performance",
            "flags",
            "logging",
        }
        unknown = [k for k in data.keys() if k not in allowed]
        if unknown:
            logging.getLogger(__name__).warning(
                "Ignoring unknown top-level config keys in indexed.toml: %s",
                ", ".join(unknown),
            )
        return {k: v for k, v in data.items() if k in allowed}

    def get(
        self, profile: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None
    ) -> IndexedSettings:
        """Load configuration with optional profile and runtime overrides."""
        # Ensure configuration scaffolding exists
        ensure_indexed_toml_exists()
        ensure_env_example(None)

        # Use cache if possible
        if (
            profile is None
            and overrides is None
            and ConfigService._settings_cache is not None
        ):
            return ConfigService._settings_cache

        if profile:
            # Manual merge of profile into base TOML; exclude profiles from validation
            toml_data = read_toml(get_config_path())
            base_config = {k: v for k, v in toml_data.items() if k != "profiles"}
            # Filter unknown top-level keys (avoid extra fields)
            base_config = self._filter_known_top_level(base_config)
            if "profiles" in toml_data and profile in toml_data["profiles"]:
                base_config = self._deep_merge(
                    base_config, toml_data["profiles"][profile]
                )
            if overrides:
                base_config = self._deep_merge(base_config, overrides)
            try:
                return IndexedSettings.model_validate(base_config)
            except Exception as exc:
                raise ValueError(
                    f"Invalid configuration with profile '{profile}': {exc}"
                ) from exc

        # Normal path: load via pydantic sources
        base_settings = IndexedSettings()
        if overrides:
            merged = self._deep_merge(base_settings.model_dump(), overrides)
            try:
                result = IndexedSettings.model_validate(merged)
            except Exception as exc:
                raise ValueError(
                    f"Invalid configuration with overrides: {exc}"
                ) from exc
        else:
            result = base_settings

        if profile is None and overrides is None:
            ConfigService._settings_cache = result
        return result

    def set(self, settings: Dict[str, Any], profile: Optional[str] = None) -> None:
        """Overwrite configuration (or a profile section)."""
        validate_no_secrets(settings)
        config_path = get_config_path()
        if profile:
            existing = read_toml(config_path)
            if "profiles" not in existing:
                existing["profiles"] = {}
            existing["profiles"][profile] = settings
            atomic_write_toml(existing, config_path)
        else:
            atomic_write_toml(settings, config_path)
        self._invalidate_cache()

    def update(self, patch: Dict[str, Any], profile: Optional[str] = None) -> None:
        """Deep-merge a patch into existing configuration."""
        validate_no_secrets(patch)
        config_path = get_config_path()
        existing = read_toml(config_path)
        if profile:
            if "profiles" not in existing:
                existing["profiles"] = {}
            if profile not in existing["profiles"]:
                existing["profiles"][profile] = {}
            existing["profiles"][profile] = self._deep_merge(
                existing["profiles"][profile], patch
            )
        else:
            base_only = {k: v for k, v in existing.items() if k != "profiles"}
            base_only = self._deep_merge(base_only, patch)
            if "profiles" in existing:
                base_only["profiles"] = existing["profiles"]
            existing = base_only
        atomic_write_toml(existing, config_path)
        self._invalidate_cache()

    def delete(self, keys: List[str], profile: Optional[str] = None) -> None:
        """Delete one or more keys from base config or a profile."""
        config_path = get_config_path()
        existing = read_toml(config_path)
        if profile:
            if "profiles" not in existing or profile not in existing["profiles"]:
                return
            target = existing["profiles"][profile]
        else:
            target = existing
        for key in keys:
            self._delete_nested_value(target, key)
        if profile and not existing["profiles"][profile]:
            del existing["profiles"][profile]
            if not existing["profiles"]:
                del existing["profiles"]
        atomic_write_toml(existing, config_path)
        self._invalidate_cache()

    def list_profiles(self) -> List[str]:
        config_data = read_toml(get_config_path())
        return list(config_data.get("profiles", {}).keys())

    def create_profile(self, name: str, config: Dict[str, Any]) -> None:
        self.set(config, profile=name)


# Convenience functions


def get_config(
    profile: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None
) -> IndexedSettings:
    return ConfigService.get_instance().get(profile=profile, overrides=overrides)


def update_config(patch: Dict[str, Any], profile: Optional[str] = None) -> None:
    ConfigService.get_instance().update(patch, profile=profile)


def set_config(settings: Dict[str, Any], profile: Optional[str] = None) -> None:
    ConfigService.get_instance().set(settings, profile=profile)


# --- Config injection gateway ---


class ConfigSlice(Enum):
    SEARCH = auto()
    CREATE = auto()
    UPDATE = auto()
    INSPECT = auto()


def _default_indexer(settings_dict: Dict[str, Any]) -> str:
    index_section = settings_dict.get("index", {}) or {}
    value = index_section.get("default_indexer")
    if isinstance(value, str) and value:
        return value
    return "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


def _extract_search(
    settings_dict: Dict[str, Any], overrides: Optional[Dict[str, Any]]
) -> Any:
    from .search_service import SearchArgs  # local import to avoid cycles
    from .models import SourceConfig  # local import

    search_section = settings_dict.get("search", {}) or {}

    # Defaults
    max_docs = int(search_section.get("max_docs", 10))
    max_chunks = int(search_section.get("max_chunks", max_docs * 3))
    include_full_text = bool(search_section.get("include_full_text", False))
    include_all_chunks = bool(search_section.get("include_all_chunks", False))
    include_matched_chunks = bool(search_section.get("include_matched_chunks", False))

    # Apply overrides if provided
    if overrides:
        if "max_docs" in overrides and overrides["max_docs"] is not None:
            max_docs = int(overrides["max_docs"])  # type: ignore[arg-type]
        if "max_chunks" in overrides and overrides["max_chunks"] is not None:
            max_chunks = int(overrides["max_chunks"])  # type: ignore[arg-type]
        if (
            "include_full_text" in overrides
            and overrides["include_full_text"] is not None
        ):
            include_full_text = bool(overrides["include_full_text"])  # type: ignore[arg-type]
        if (
            "include_all_chunks" in overrides
            and overrides["include_all_chunks"] is not None
        ):
            include_all_chunks = bool(overrides["include_all_chunks"])  # type: ignore[arg-type]
        if (
            "include_matched_chunks" in overrides
            and overrides["include_matched_chunks"] is not None
        ):
            include_matched_chunks = bool(overrides["include_matched_chunks"])  # type: ignore[arg-type]

    # Optional single-collection scope
    configs = None
    if overrides and overrides.get("collection"):
        indexer = overrides.get("index_name") or _default_indexer(settings_dict)
        cfg = SourceConfig(
            name=str(overrides["collection"]),
            type="localFiles",
            base_url_or_path="",
            indexer=str(indexer),
        )
        configs = [cfg]

    return SearchArgs(
        configs=configs,
        max_chunks=max_chunks,
        max_docs=max_docs,
        include_full_text=include_full_text,
        include_all_chunks=include_all_chunks,
        include_matched_chunks=include_matched_chunks,
    )


def _extract_inspect(
    settings_dict: Dict[str, Any], overrides: Optional[Dict[str, Any]]
) -> Any:
    from .inspect_service import InspectArgs  # local import to avoid cycles

    mcp_section = settings_dict.get("mcp", {}) or {}
    include_index_size = bool(mcp_section.get("include_index_size", False))
    if (
        overrides
        and "include_index_size" in overrides
        and overrides["include_index_size"] is not None
    ):
        include_index_size = bool(overrides["include_index_size"])  # type: ignore[arg-type]
    return InspectArgs(include_index_size=include_index_size)


def _extract_create(
    settings_dict: Dict[str, Any], overrides: Optional[Dict[str, Any]]
) -> Any:
    from .collection_service import CreateArgs  # local import to avoid cycles

    if not overrides or "configs" not in overrides:
        raise ValueError(
            "CreateArgs requires 'configs' in overrides (List[SourceConfig])."
        )
    configs = overrides["configs"]
    use_cache = bool(overrides.get("use_cache", True))
    force = bool(overrides.get("force", False))
    return CreateArgs(configs=configs, use_cache=use_cache, force=force)


def _extract_update(
    settings_dict: Dict[str, Any], overrides: Optional[Dict[str, Any]]
) -> Any:
    from .collection_service import UpdateArgs  # local import to avoid cycles

    if not overrides or "configs" not in overrides:
        raise ValueError(
            "UpdateArgs requires 'configs' in overrides (List[SourceConfig])."
        )
    configs = overrides["configs"]
    return UpdateArgs(configs=configs)


def resolve_and_extract(
    kind: ConfigSlice,
    *,
    profile: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
    target: Optional[str] = None,
) -> Tuple[Dict[str, Any], Any]:
    """Resolve settings via ConfigService and extract operation-specific args.

    Returns (settings_dict, args_dto) for the requested slice.
    """
    settings = ConfigService.get_instance().get(profile=profile, overrides=overrides)
    settings_dict = settings.model_dump()

    if kind is ConfigSlice.SEARCH:
        return settings_dict, _extract_search(settings_dict, overrides)
    if kind is ConfigSlice.INSPECT:
        return settings_dict, _extract_inspect(settings_dict, overrides)
    if kind is ConfigSlice.CREATE:
        return settings_dict, _extract_create(settings_dict, overrides)
    if kind is ConfigSlice.UPDATE:
        return settings_dict, _extract_update(settings_dict, overrides)

    raise ValueError(f"Unsupported ConfigSlice: {kind}")
