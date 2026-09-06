"""Shared fakes for GitHub GraphQL reader tests — mirrors Outline's
`_FakeAsyncClient` pattern (tests/unit/indexed/connectors/outline/test_reader_integration.py)."""

from __future__ import annotations

from typing import Any, Callable


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeAsyncClient:
    """Stands in for `httpx.AsyncClient`. `router` maps a GraphQL request body
    (parsed `{"query": ..., "variables": ...}`) to a `FakeResponse`."""

    def __init__(
        self, router: Callable[[dict[str, Any]], FakeResponse], **kwargs: Any
    ) -> None:
        self._router = router

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._router(kwargs.get("json", {}))
