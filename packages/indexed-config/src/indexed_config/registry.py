"""Configuration spec registry."""

from __future__ import annotations

from typing import Dict, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ConfigRegistry:
    """Registry of typed configuration specs keyed by dot-path."""

    def __init__(self) -> None:
        self._specs: Dict[str, Type[BaseModel]] = {}

    def register(self, spec: Type[T], *, path: str) -> None:
        """Register a Pydantic model as the config schema for a dot-path."""
        self._specs[path] = spec

    @property
    def specs(self) -> Dict[str, Type[BaseModel]]:
        """Return a read-only view of registered specs."""
        return self._specs

    def has(self, path: str) -> bool:
        """Check if a spec is registered at the given path."""
        return path in self._specs
