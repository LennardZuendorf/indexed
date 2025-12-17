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
        """
        Initialize the Provider with typed configuration slices, the merged raw configuration, and an optional mapping from dot-paths to model types.
        
        Parameters:
            slices (Dict[type, BaseModel]): Mapping from Pydantic model types to their corresponding configuration instances; treated as the immutable typed view.
            raw (Dict[str, Any]): The raw merged configuration dictionary.
            path_to_type (Dict[str, Type[BaseModel]] | None): Optional mapping from dot-separated config paths to Pydantic model types; defaults to an empty dict when omitted.
        """
        self._slices = slices
        self._raw = raw
        self._path_to_type = path_to_type or {}

    def get(self, spec: Type[T]) -> T:
        """
        Retrieve the configuration instance associated with the given Pydantic model type.
        
        Parameters:
            spec: Pydantic model class whose registered configuration instance to return.
        
        Returns:
            The configuration instance corresponding to `spec`.
        
        Raises:
            KeyError: If `spec` is not registered in this provider.
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
            path: Dot-separated path (e.g., 'sources.jira').
            
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
        """
        Return the underlying merged configuration dictionary.
        
        Returns:
            Dict[str, Any]: The raw merged configuration mapping.
        """
        return self._raw