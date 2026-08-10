"""Configuration spec registry."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ConfigRegistry:
    """Registry of typed configuration specs keyed by dot-path."""

    def __init__(self) -> None:
        self._specs: dict[str, type[BaseModel]] = {}

    def register(self, spec: type[T], *, path: str) -> None:
        """Register a Pydantic model as the config schema for a dot-path."""
        self._specs[path] = spec

    @property
    def specs(self) -> dict[str, type[BaseModel]]:
        """Return a read-only view of registered specs."""
        return self._specs

    def has(self, path: str) -> bool:
        """Check if a spec is registered at the given path."""
        return path in self._specs
