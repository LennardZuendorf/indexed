from __future__ import annotations

from typing import Any, Dict, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Provider:
    """Typed view over merged config. Immutable snapshot."""

    def __init__(
        self,
        slices: Dict[type, BaseModel],
        raw: Dict[str, Any],
        path_to_type: Dict[str, Type[BaseModel]] | None = None,
    ) -> None:
        self._slices = slices
        self._raw = raw
        self._path_to_type = path_to_type or {}

    def get(self, spec: Type[T]) -> T:
        """Get config instance by type.
        
        Args:
            spec: Pydantic model class type.
            
        Returns:
            Validated config instance.
            
        Raises:
            KeyError: If spec not registered or not found in config.
        """
        if spec not in self._slices:
            raise KeyError(
                f"Config spec {spec.__name__} not found. "
                "Did you register it with config.register()?"
            )
        return self._slices[spec]  # type: ignore[return-value]

    def get_by_path(self, path: str) -> BaseModel:
        """Get config instance by dot path.
        
        Args:
            path: Dot-separated path (e.g., 'sources.jira_cloud').
            
        Returns:
            Validated config instance.
            
        Raises:
            KeyError: If path not registered or not found in config.
        """
        if path not in self._path_to_type:
            raise KeyError(
                f"Config path '{path}' not found. "
                "Did you register it with config.register()?"
            )
        spec = self._path_to_type[path]
        return self._slices[spec]

    @property
    def raw(self) -> Dict[str, Any]:
        """Get raw merged config dictionary."""
        return self._raw
