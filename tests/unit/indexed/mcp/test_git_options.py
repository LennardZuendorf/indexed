"""MCP search tools must FORWARD the git options (and honour the config default).

The CLI twin of this contract is ``TestGitFlags`` in
``tests/unit/indexed/knowledge/commands/test_search.py``. Before this, a rename
or a dropped kwarg in either tool closure failed no test (#279 review,
findings 2 and 3).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import indexed.mcp.tools as tools_module
from indexed.core.v1.config_models import CoreV1SearchConfig
from indexed.mcp.server import mcp


def _get_tool(name: str):
    return asyncio.run(mcp.get_tool(name))


def run_async(coro_or_result):
    """Run coroutine synchronously or return result directly if not a coroutine."""
    if asyncio.iscoroutine(coro_or_result):
        return asyncio.run(coro_or_result)
    return coro_or_result


def _cfg(**overrides) -> CoreV1SearchConfig:
    return CoreV1SearchConfig(**overrides)


class TestSearchToolGitOptions:
    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_both_options_reach_svc_search(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(
            _get_tool("search").fn(
                "q", changed_since="HEAD~1", git_provenance=True, ctx=scoped("col")
            )
        )

        kwargs = mock_search.call_args.kwargs
        assert kwargs["changed_since"] == "HEAD~1"
        assert kwargs["git_provenance"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_omitted_options_forward_nothing(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(_get_tool("search").fn("q", ctx=scoped("col")))

        kwargs = mock_search.call_args.kwargs
        assert "changed_since" not in kwargs
        assert "git_provenance" not in kwargs

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_configured_default_applies_when_flag_omitted(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        """``core.v1.search.git_provenance`` must work on MCP, not just the CLI."""
        mock_resolve_config.return_value = _cfg(git_provenance=True)
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(_get_tool("search").fn("q", ctx=scoped("col")))

        assert mock_search.call_args.kwargs["git_provenance"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_explicit_false_beats_the_configured_default(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg(git_provenance=True)
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(_get_tool("search").fn("q", git_provenance=False, ctx=scoped("col")))

        assert mock_search.call_args.kwargs["git_provenance"] is False

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_line_blame_reaches_svc_search(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(_get_tool("search").fn("q", git_line_blame=True, ctx=scoped("col")))

        assert mock_search.call_args.kwargs["git_line_blame"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_line_blame_configured_default_applies(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg(git_line_blame=True)
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(_get_tool("search").fn("q", ctx=scoped("col")))

        assert mock_search.call_args.kwargs["git_line_blame"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_line_blame_explicit_false_beats_the_default(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg(git_line_blame=True)
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(_get_tool("search").fn("q", git_line_blame=False, ctx=scoped("col")))

        assert mock_search.call_args.kwargs["git_line_blame"] is False


class TestSearchCollectionToolGitOptions:
    def _status(self, name: str, indexers: list[str], source_type: str) -> MagicMock:
        status = MagicMock()
        status.name = name
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
        scoped: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [self._status("col", ["default"], "localFiles")]
        mock_search.return_value = {}

        run_async(
            _get_tool("search_collection").fn(
                "col",
                "q",
                changed_since="HEAD",
                git_provenance=True,
                git_line_blame=True,
                ctx=scoped("col"),
            )
        )

        kwargs = mock_search.call_args.kwargs
        assert kwargs["changed_since"] == "HEAD"
        assert kwargs["git_provenance"] is True
        assert kwargs["git_line_blame"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_omitted_options_forward_nothing(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [self._status("col", ["default"], "localFiles")]
        mock_search.return_value = {}

        run_async(_get_tool("search_collection").fn("col", "q", ctx=scoped("col")))

        kwargs = mock_search.call_args.kwargs
        assert "changed_since" not in kwargs
        assert "git_provenance" not in kwargs
        assert "git_line_blame" not in kwargs
        assert "include_freshness" not in kwargs

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_freshness_reaches_svc_search(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
    ) -> None:
        """The #146 advisory is opt-in and must reach the facade (both tools)."""
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [self._status("col", ["default"], "localFiles")]
        mock_search.return_value = {}

        run_async(
            _get_tool("search").fn("q", include_freshness=True, ctx=scoped("col"))
        )
        assert mock_search.call_args.kwargs["include_freshness"] is True

        run_async(
            _get_tool("search_collection").fn(
                "col", "q", include_freshness=True, ctx=scoped("col")
            )
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
        scoped: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg(git_provenance=True)
        mock_status.return_value = [self._status("col", ["default"], "localFiles")]
        mock_search.return_value = {}

        run_async(_get_tool("search_collection").fn("col", "q", ctx=scoped("col")))

        assert mock_search.call_args.kwargs["git_provenance"] is True


class TestSearchToolRerankOption:
    """``git_rerank`` must reach the engine from MCP and honour the config default."""

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_explicit_flag_reaches_svc_search(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_status.return_value = [mcp_status("col")]
        mock_search.return_value = {}

        run_async(_get_tool("search").fn("q", git_rerank=True, ctx=scoped("col")))

        assert mock_search.call_args.kwargs["git_rerank"] is True

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_config_default_enables_it_and_explicit_false_wins(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
        mcp_status: Any,
    ) -> None:
        mock_search.return_value = {}
        mock_resolve_config.return_value = _cfg(git_rerank=True)
        mock_status.return_value = [mcp_status("col")]

        run_async(_get_tool("search").fn("q", ctx=scoped("col")))
        assert mock_search.call_args.kwargs["git_rerank"] is True

        run_async(_get_tool("search").fn("q", git_rerank=False, ctx=scoped("col")))
        assert mock_search.call_args.kwargs["git_rerank"] is False

    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_collection_tool_forwards_it_too(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
        mock_status: MagicMock,
        scoped: Any,
    ) -> None:
        mock_resolve_config.return_value = _cfg()
        mock_search.return_value = {}
        status = MagicMock()
        status.name = "col1"
        status.indexers = ["default"]
        status.source_type = "localFiles"

        mock_status.return_value = [status]
        run_async(
            _get_tool("search_collection").fn(
                "col1", "q", git_rerank=True, ctx=scoped("col1")
            )
        )

        assert mock_search.call_args.kwargs["git_rerank"] is True
