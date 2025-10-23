from __future__ import annotations

from typing import Any, Dict, List, Tuple, Type, TypeVar
from pydantic import BaseModel, ValidationError

from .path_utils import get_by_path, set_by_path, delete_by_path
from .store import TomlStore
from .provider import Provider

T = TypeVar("T", bound=BaseModel)


class ConfigService:
    """Singleton registry + I/O for application configuration.

    - register(spec, path): declare a typed slice at a dot-path
    - bind(): load+merge+validate all registered specs and return Provider
    - get/set/delete: operate on raw mapping (workspace TOML as write target)
    - validate(): validate all specs; returns list of (path, error)
    """

    _instance: "ConfigService" | None = None

    def __init__(self) -> None:
        self._specs: Dict[str, Type[BaseModel]] = {}
        self._store = TomlStore()

    @classmethod
    def instance(cls) -> "ConfigService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # Registry
    def register(self, spec: Type[T], *, path: str) -> None:
        self._specs[path] = spec

    # I/O
    def load_raw(self) -> Dict[str, Any]:
        return self._store.read()

    def save_raw(self, data: Dict[str, Any]) -> None:
        self._store.write(data)

    # Typed binding
    def bind(self) -> Provider:
        raw = self.load_raw()
        instances: Dict[type, BaseModel] = {}
        for path, spec in self._specs.items():
            payload = get_by_path(raw, path, default=None)
            # Skip specs that are not present in config (optional sections)
            if payload in (None, {}):
                continue
            try:
                instances[spec] = spec.model_validate(payload)  # type: ignore[arg-type]
            except ValidationError as exc:
                # Surface early by raising; caller can handle
                raise ValueError(f"Invalid config for '{path}': {exc}") from exc
        return Provider(instances, raw)

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
