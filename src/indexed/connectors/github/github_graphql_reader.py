"""Async GraphQL v4 reader for GitHub issues, pull requests, and Projects v2 boards."""

from __future__ import annotations

import asyncio
import time
from typing import Iterator

import httpx
from loguru import logger

from . import queries


class GitHubGraphQLError(Exception):
    """Raised when the GitHub GraphQL API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GitHub GraphQL error ({status_code}): {message}")
        self.status_code = status_code
        self.message = message


class GitHubGraphQLReader:
    """Reads issues (and, in later tasks, pull requests and Projects v2 boards)
    from GitHub via the GraphQL v4 API.

    Pages each repo's issues sequentially via cursor pagination, with requests
    bounded by a semaphore and retried with backoff on rate limiting.

    Args:
        graphql_url: GraphQL endpoint (Cloud or Enterprise).
        token: Bearer token for authentication.
        repos: (owner, name) tuples to read issues from.
        project: (owner, number) Projects v2 board selector, or None. Unused
            until Task 4 adds Projects v2 board support.
        state: Issue state filter — "open", "closed", or "all".
        labels: Restrict to issues carrying any of these labels. None = all.
        include_pull_requests: Also read pull requests. Unused until Task 4.
        include_comments: Fetch and attach issue comments.
        page_size: Nodes per GraphQL page request.
        max_concurrent_requests: Max concurrent in-flight GraphQL requests.
        verify_ssl: Verify TLS certificates (set False for self-signed CAs).
        modified_since: ISO timestamp cutoff for incremental updates.
        number_of_retries: Max attempts per request before raising.
        retry_delay: Base delay in seconds between retries (doubles each attempt).
    """

    def __init__(
        self,
        graphql_url: str,
        token: str,
        repos: list[tuple[str, str]],
        project: tuple[str, int] | None,
        state: str,
        labels: list[str] | None,
        include_pull_requests: bool,
        include_comments: bool,
        page_size: int = 100,
        max_concurrent_requests: int = 5,
        verify_ssl: bool = True,
        modified_since: str | None = None,
        number_of_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self._graphql_url = graphql_url
        self._auth_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        self._repos = repos
        self._project = project
        self._state = state
        self._labels = labels
        self._include_pull_requests = include_pull_requests
        self._include_comments = include_comments
        self._page_size = page_size
        self._max_concurrent_requests = max_concurrent_requests
        self._verify_ssl = verify_ssl
        self._modified_since = modified_since
        self._number_of_retries = number_of_retries
        self._retry_delay = retry_delay
        if not verify_ssl:
            logger.warning(
                "GitHub: TLS certificate verification is DISABLED (verify_ssl=False). "
                "Your token may be exposed to a man-in-the-middle. Only use this for "
                "trusted Enterprise Server instances with self-signed certificates."
            )

    # ------------------------------------------------------------------
    # DocumentReader protocol
    # ------------------------------------------------------------------

    def get_number_of_documents(self) -> int:
        return len(list(self.read_all_documents()))

    def read_all_documents(self) -> Iterator[dict]:
        """Yield raw issue documents across all configured repos, deduplicated by id."""
        documents = asyncio.run(self._read_all_async())
        seen: set[str] = set()
        for doc in documents:
            if doc["id"] in seen:
                continue
            seen.add(doc["id"])
            yield doc

    def get_reader_details(self) -> dict:
        return {
            "type": "github",
            "graphqlUrl": self._graphql_url,
            "repos": [f"{owner}/{name}" for owner, name in self._repos],
            "project": f"{self._project[0]}/{self._project[1]}"
            if self._project
            else None,
            "state": self._state,
            "labels": self._labels,
            "includePullRequests": self._include_pull_requests,
            "includeComments": self._include_comments,
            "pageSize": self._page_size,
            "maxConcurrentRequests": self._max_concurrent_requests,
            "verifySsl": self._verify_ssl,
        }

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def _read_all_async(self) -> list[dict]:
        async with httpx.AsyncClient(
            headers=self._auth_headers,
            timeout=30.0,
            verify=self._verify_ssl,
            limits=httpx.Limits(
                max_connections=self._max_concurrent_requests,
                max_keepalive_connections=5,
            ),
        ) as client:
            semaphore = asyncio.Semaphore(self._max_concurrent_requests)
            tasks = [
                self._fetch_issues(client, semaphore, owner, name)
                for owner, name in self._repos
            ]
            results = await asyncio.gather(*tasks)
            documents: list[dict] = []
            for batch in results:
                documents.extend(batch)
            return documents

    async def _fetch_issues(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        owner: str,
        name: str,
    ) -> list[dict]:
        documents: list[dict] = []
        after: str | None = None
        states = self._graphql_states()
        while True:
            data = await self._post_graphql(
                client,
                semaphore,
                queries.ISSUES_QUERY,
                {
                    "owner": owner,
                    "name": name,
                    "first": self._page_size,
                    "after": after,
                    "states": states,
                    "labels": self._labels,
                    "since": self._modified_since,
                },
            )
            issues = data["repository"]["issues"]
            for node in issues["nodes"]:
                documents.append(self._issue_to_document(owner, name, node))
            page_info = issues["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            after = page_info["endCursor"]
        return documents

    def _issue_to_document(self, owner: str, name: str, node: dict) -> dict:
        comments = []
        if self._include_comments:
            comments = [
                {
                    "author": c["author"]["login"] if c.get("author") else None,
                    "body": c["body"],
                }
                for c in node.get("comments", {}).get("nodes", [])
            ]
        return {
            "id": f"{owner}/{name}#{node['number']}",
            "url": node["url"],
            "modifiedTime": node["updatedAt"],
            "title": node["title"],
            "body": node.get("body") or "",
            "state": node["state"],
            "labels": [
                label["name"] for label in node.get("labels", {}).get("nodes", [])
            ],
            "author": node["author"]["login"] if node.get("author") else None,
            "kind": "issue",
            "comments": comments,
            "project_fields": {},
        }

    def _graphql_states(self) -> list[str] | None:
        if self._state == "all":
            return None
        return [self._state.upper()]

    # ------------------------------------------------------------------
    # GraphQL transport: retry + rate-limit backoff
    # ------------------------------------------------------------------

    async def _post_graphql(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        query: str,
        variables: dict,
    ) -> dict:
        async with semaphore:
            last_error: GitHubGraphQLError | None = None
            for attempt in range(self._number_of_retries):
                response = await client.post(
                    self._graphql_url, json={"query": query, "variables": variables}
                )
                if response.status_code in (403, 429):
                    last_error = GitHubGraphQLError(
                        response.status_code, "rate limited"
                    )
                    logger.warning(
                        f"GitHub GraphQL rate limited (HTTP {response.status_code}), "
                        f"retrying (attempt {attempt + 1}/{self._number_of_retries})"
                    )
                    await self._backoff(response, attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                errors = payload.get("errors")
                if errors:
                    if any(e.get("type") == "RATE_LIMITED" for e in errors):
                        last_error = GitHubGraphQLError(
                            response.status_code, str(errors)
                        )
                        logger.warning(
                            f"GitHub GraphQL rate limited, retrying "
                            f"(attempt {attempt + 1}/{self._number_of_retries})"
                        )
                        await self._backoff(response, attempt)
                        continue
                    raise GitHubGraphQLError(response.status_code, str(errors))
                return payload["data"]
            raise last_error or GitHubGraphQLError(
                0, "GraphQL request failed after retries"
            )

    async def _backoff(self, response: httpx.Response, attempt: int) -> None:
        reset_header = response.headers.get("X-RateLimit-Reset")
        delay = self._retry_delay * (2**attempt)
        if reset_header:
            try:
                delay = max(float(reset_header) - time.time(), self._retry_delay)
            except ValueError:
                pass
        await asyncio.sleep(min(max(delay, 0.0), 60.0))
