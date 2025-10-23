from __future__ import annotations

from typing import Any, Dict, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Provider:
    """Typed view over merged config. Immutable snapshot."""

    def __init__(self, slices: Dict[type, BaseModel], raw: Dict[str, Any]) -> None:
        self._slices = slices
        self._raw = raw

    def get(self, spec: Type[T]) -> T:
        return self._slices[spec]  # type: ignore[return-value]

    @property
    def raw(self) -> Dict[str, Any]:
        return self._raw
