"""GitHubConnector: wires the GraphQL reader + converter into a BaseConnector."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, ClassVar

from indexed.config import ConfigService, ConfigurationError
from indexed.protocols import ConnectorMetadata, ConnectorRun, Manifest

from .github_document_converter import GitHubDocumentConverter
from .github_graphql_reader import GitHubGraphQLReader
from .schema import GitHubConfig

# Optional GitHub reader settings carried forward on an incremental update:
# (manifest camelCase key, config snake_key). Only applied when present in the
# stored manifest, so an unset key keeps the connector's own default.
_OPTIONAL_OVERLAYS = (
    ("repos", "repos"),
    ("project", "project"),
    ("host", "host"),
    ("graphqlUrl", "graphql_url"),
    ("state", "state"),
    ("labels", "labels"),
    ("includePullRequests", "include_pull_requests"),
    ("includeComments", "include_comments"),
    ("pageSize", "page_size"),
    ("maxConcurrentRequests", "max_concurrent_requests"),
    ("verifySsl", "verify_ssl"),
)


def _with_safety_buffer(modified_since: str | None, buffer_seconds: int = 60) -> str | None:
    """Shift a stored cutoff back by a safety buffer to avoid missing items
    updated mid-crawl (GitHub's updatedAt cursor ordering can otherwise skip
    an item modified during the fetch window)."""
    if not modified_since:
        return None
    cutoff = datetime.fromisoformat(modified_since.replace("Z", "+00:00"))
    buffered = cutoff - timedelta(seconds=buffer_seconds)
    return buffered.isoformat().replace("+00:00", "Z")


class GitHubConnector:
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="github",
        display_name="GitHub (Cloud, Enterprise Cloud, or Enterprise Server)",
        description="Index GitHub issues, pull requests, and Projects v2 boards",
        config_class=GitHubConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create github --repo octo/hello",
    )

    def __init__(self, config: GitHubConfig) -> None:
        if not config.repos and not config.project:
            raise ConfigurationError(
                "GitHub source needs at least one of 'repos' or 'project' configured."
            )

        self._config = config
        token = config.get_token()

        self._reader = GitHubGraphQLReader(
            graphql_url=config.resolve_graphql_url(),
            token=token,
            host=config.host,
            repos=config.parsed_repos(),
            project=config.parsed_project(),
            state=config.state,
            labels=config.labels,
            include_pull_requests=config.include_pull_requests,
            include_comments=config.include_comments,
            page_size=config.page_size,
            max_concurrent_requests=config.max_concurrent_requests,
            verify_ssl=config.verify_ssl,
            modified_since=config.modified_since,
        )
        self._converter = GitHubDocumentConverter(
            max_chunk_tokens=config.max_chunk_tokens
        )

    @property
    def reader(self) -> GitHubGraphQLReader:
        return self._reader

    @property
    def converter(self) -> GitHubDocumentConverter:
        return self._converter

    @property
    def connector_type(self) -> str:
        return "github"

    def __repr__(self) -> str:
        deployment = "Cloud" if self._config.is_cloud() else "Enterprise"
        return f"GitHubConnector(host='{self._config.host}', deployment='{deployment}')"

    @classmethod
    def config_spec(cls) -> dict:
        return {
            "repos": {
                "type": "list[str]",
                "required": False,
                "secret": False,
                "default": [],
                "description": "owner/repo selectors",
            },
            "project": {
                "type": "str",
                "required": False,
                "secret": False,
                "default": None,
                "description": "owner/number Projects v2 board",
            },
            "host": {
                "type": "str",
                "required": False,
                "secret": False,
                "default": "github.com",
                "description": "github.com, SUBDOMAIN.ghe.com, or a GHES hostname",
            },
            "graphql_url": {
                "type": "str",
                "required": False,
                "secret": False,
                "default": None,
                "description": "explicit GraphQL endpoint override",
            },
            "verify_ssl": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": True,
                "description": "set false for GHES self-signed CAs",
            },
            "token": {
                "type": "str",
                "required": False,
                "secret": True,
                "default": "GITHUB_TOKEN",
                "description": "GitHub access token",
            },
            "state": {
                "type": "str",
                "required": False,
                "secret": False,
                "default": "all",
                "description": "open, closed, or all",
            },
            "labels": {
                "type": "list[str]",
                "required": False,
                "secret": False,
                "default": None,
                "description": "label filter",
            },
            "include_pull_requests": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": False,
                "description": "include pull request threads",
            },
            "include_comments": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": True,
                "description": "include issue/PR comments",
            },
            "max_chunk_tokens": {
                "type": "int",
                "required": False,
                "secret": False,
                "default": 512,
                "description": "max tokens per chunk",
            },
            "page_size": {
                "type": "int",
                "required": False,
                "secret": False,
                "default": 100,
                "description": "GraphQL page size",
            },
            "max_concurrent_requests": {
                "type": "int",
                "required": False,
                "secret": False,
                "default": 5,
                "description": "concurrent GraphQL requests",
            },
        }

    @classmethod
    def from_config(cls, config_service: ConfigService) -> "GitHubConnector":
        config_service.register(GitHubConfig, path="sources.github")
        provider = config_service.bind()
        cfg = provider.get(GitHubConfig)
        return cls(cfg)

    @classmethod
    def from_manifest(
        cls, manifest: Manifest, config_service: Any, *, storage_path: str
    ) -> ConnectorRun:
        """Rebuild the GitHub connector for an incremental update.

        Carries the stored reader settings forward as in-memory overlays and
        sets the incremental cutoff via ``modified_since``, buffered 60s back
        from ``lastModifiedDocumentTime`` to tolerate concurrent edits during
        the previous fetch window.
        """
        rd = manifest.reader.model_dump(by_alias=True)
        if not rd.get("repos") and not rd.get("project"):
            raise ConfigurationError(
                f"GitHub manifest for collection '{manifest.collection_name}' is missing both "
                "'repos' and 'project'; cannot rebuild connector for incremental update"
            )

        ns = "sources.github"
        overlay = config_service.set_overlay
        for manifest_key, config_key in _OPTIONAL_OVERLAYS:
            if rd.get(manifest_key) is not None:
                overlay(f"{ns}.{config_key}", rd[manifest_key])

        since = _with_safety_buffer(manifest.last_modified_document_time)
        if since is not None:
            overlay(f"{ns}.modified_since", since)

        connector = cls.from_config(config_service)
        return ConnectorRun(connector.reader, connector.converter, [], None)


__all__ = ["GitHubConnector"]
