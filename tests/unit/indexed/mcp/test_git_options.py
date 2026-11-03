"""MCP search tools must FORWARD the git options (and honour the config default).

The CLI twin of this contract is ``TestGitFlags`` in
``tests/unit/indexed/knowledge/commands/test_search.py``. Before this, a rename
or a dropped kwarg in either tool closure failed no test (#279 review,
findings 2 and 3).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import indexed.mcp.tools as tools_module
from indexed.core.v1.config_models import CoreV1SearchConfig
from indexed.mcp.server import mcp


def _get_tool(name: str):
    return asyncio.run(mcp.get_tool(name))


def _ctx() -> MagicMock:
    """Minimal lifespan state: a global collections path, no stored configs."""
    ctx = MagicMock()
    ctx.lifespan_context = {"cli_context": SimpleNamespace(collections_path="/cols")}
    return ctx


def _cfg(**overrides) -> CoreV1SearchConfig:
    return CoreV1SearchConfig(**overrides)


class TestSearchToolGitOptions:
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_both_options_reach_svc_search(
        self, mock_resolve_config: MagicMock, mock_search: MagicMock
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_search.return_value = {}

        _get_tool("search").fn(
            "q", changed_since="HEAD~1", git_provenance=True, ctx=_ctx()
        )

        kwargs = mock_search.call_args.kwargs
        assert kwargs["changed_since"] == "HEAD~1"
        assert kwargs["git_provenance"] is True

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_omitted_options_forward_nothing(
        self, mock_resolve_config: MagicMock, mock_search: MagicMock
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_search.return_value = {}

        _get_tool("search").fn("q", ctx=_ctx())

        kwargs = mock_search.call_args.kwargs
        assert "changed_since" not in kwargs
        assert "git_provenance" not in kwargs

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_configured_default_applies_when_flag_omitted(
        self, mock_resolve_config: MagicMock, mock_search: MagicMock
    ) -> None:
        """``core.v1.search.git_provenance`` must work on MCP, not just the CLI."""
        mock_resolve_config.return_value = _cfg(git_provenance=True)
        mock_search.return_value = {}

        _get_tool("search").fn("q", ctx=_ctx())

        assert mock_search.call_args.kwargs["git_provenance"] is True

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_explicit_false_beats_the_configured_default(
        self, mock_resolve_config: MagicMock, mock_search: MagicMock
    ) -> None:
        mock_resolve_config.return_value = _cfg(git_provenance=True)
        mock_search.return_value = {}

        _get_tool("search").fn("q", git_provenance=False, ctx=_ctx())

        assert mock_search.call_args.kwargs["git_provenance"] is False


class TestSearchCollectionToolGitOptions:
    def _status(self, indexers: list[str], source_type: str) -> MagicMock:
        status = MagicMock()
        status.indexers = indexers
        status.source_type = source_type
        return status

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_both_options_reach_svc_search(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [self._status(["default"], "localFiles")]
        mock_search.return_value = {}

        _get_tool("search_collection").fn(
            "col", "q", changed_since="HEAD", git_provenance=True, ctx=_ctx()
        )

        kwargs = mock_search.call_args.kwargs
        assert kwargs["changed_since"] == "HEAD"
        assert kwargs["git_provenance"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_omitted_options_forward_nothing(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [self._status(["default"], "localFiles")]
        mock_search.return_value = {}

        _get_tool("search_collection").fn("col", "q", ctx=_ctx())

        kwargs = mock_search.call_args.kwargs
        assert "changed_since" not in kwargs
        assert "git_provenance" not in kwargs
        assert "include_freshness" not in kwargs

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_freshness_reaches_svc_search(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """The #146 advisory is opt-in and must reach the facade (both tools)."""
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [self._status(["default"], "localFiles")]
        mock_search.return_value = {}

        _get_tool("search").fn("q", include_freshness=True, ctx=_ctx())
        assert mock_search.call_args.kwargs["include_freshness"] is True

        _get_tool("search_collection").fn(
            "col", "q", include_freshness=True, ctx=_ctx()
        )
        assert mock_search.call_args.kwargs["include_freshness"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_configured_default_applies_when_flag_omitted(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = _cfg(git_provenance=True)
        mock_status.return_value = [self._status(["default"], "localFiles")]
        mock_search.return_value = {}

        _get_tool("search_collection").fn("col", "q", ctx=_ctx())

        assert mock_search.call_args.kwargs["git_provenance"] is True
