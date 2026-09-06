"""Pydantic config for the GitHub connector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import auth

GITHUB_CLOUD_HOST = "github.com"


class GitHubConfig(BaseModel):
    """Configuration for GitHub (Cloud or self-hosted Enterprise)."""

    repos: list[str] = Field(default_factory=list)
    project: str | None = None
    host: str = GITHUB_CLOUD_HOST
    graphql_url: str | None = None
    verify_ssl: bool = True
    token: str | None = None
    state: Literal["open", "closed", "all"] = "all"
    labels: list[str] | None = None
    include_pull_requests: bool = False
    include_comments: bool = True
    max_chunk_tokens: int = Field(default=512, ge=64, le=2048)
    page_size: int = Field(default=100, ge=1, le=100)
    max_concurrent_requests: int = Field(default=5, ge=1, le=20)
    modified_since: str | None = None

    @field_validator("host", mode="before")
    @classmethod
    def _strip_host(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        return v.removeprefix("https://").removeprefix("http://").strip("/")

    def get_token(self) -> str:
        """Get the GitHub token from config or environment."""
        return auth.resolve_token(self.token)

    def resolve_graphql_url(self) -> str:
        """Resolve the GraphQL endpoint URL based on host.

        Returns:
            - Explicit graphql_url if set
            - api.github.com/graphql for github.com
            - api.<host>/graphql for .ghe.com data residency
            - <host>/api/graphql for GitHub Enterprise Server
        """
        if self.graphql_url:
            return self.graphql_url
        if self.host == GITHUB_CLOUD_HOST:
            return "https://api.github.com/graphql"
        if self.host.endswith(".ghe.com"):
            return f"https://api.{self.host}/graphql"
        return f"https://{self.host}/api/graphql"

    def is_cloud(self) -> bool:
        """Check if this config targets GitHub Cloud."""
        return self.host == GITHUB_CLOUD_HOST

    def parsed_repos(self) -> list[tuple[str, str]]:
        """Parse repo selectors into (owner, name) tuples.

        Raises:
            ValueError: If any repo selector is not in 'owner/repo' format
        """
        result: list[tuple[str, str]] = []
        for entry in self.repos:
            owner, _, name = entry.partition("/")
            if not owner or not name:
                raise ValueError(f"Invalid repo selector {entry!r}; expected 'owner/repo'")
            result.append((owner, name))
        return result

    def parsed_project(self) -> tuple[str, int] | None:
        """Parse project selector into (owner, number) tuple.

        Returns:
            (owner, project_number) if project is set, None otherwise

        Raises:
            ValueError: If project is not in 'owner/number' format
        """
        if not self.project:
            return None
        owner, _, number = self.project.partition("/")
        if not owner or not number.isdigit():
            raise ValueError(
                f"Invalid project selector {self.project!r}; expected 'owner/number'"
            )
        return owner, int(number)


__all__ = ["GitHubConfig", "GITHUB_CLOUD_HOST"]
