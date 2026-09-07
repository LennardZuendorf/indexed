"""GitHubConnector: wires the GraphQL reader + converter into a BaseConnector."""

from __future__ import annotations

from typing import Any, ClassVar

from indexed.config import ConfigService, ConfigurationError
from indexed.protocols import ConnectorMetadata, ConnectorRun, Manifest

from .github_document_converter import GitHubDocumentConverter
from .github_graphql_reader import GitHubGraphQLReader
from .schema import GitHubConfig


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
        raise NotImplementedError("Implemented in Task 7 (incremental update)")


__all__ = ["GitHubConnector"]
