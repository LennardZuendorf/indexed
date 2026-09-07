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
    """Reads issues, pull requests, and Projects v2 boards from GitHub via the
    GraphQL v4 API.

    Pages each repo's issues and pull requests sequentially via cursor
    pagination, with requests bounded by a semaphore and retried with backoff
    on rate limiting.

    Args:
        graphql_url: GraphQL endpoint (Cloud or Enterprise).
        token: Bearer token for authentication.
        repos: (owner, name) tuples to read issues from.
        project: (owner, number) Projects v2 board selector, or None.
        state: Issue state filter — "open", "closed", or "all".
        labels: Restrict to issues carrying any of these labels. None = all.
        include_pull_requests: Also read pull requests.
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
        self._cached_documents: list[dict] | None = None
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
        return len(self._fetch_documents())

    def read_all_documents(self) -> Iterator[dict]:
        """Yield raw issue documents across all configured repos, deduplicated by id.

        A document reachable via more than one source (e.g. a repo scan and a
        project board) is emitted once, carrying the union of every copy's
        project_fields — non-empty values win, and later copies take
        precedence on overlapping field names — so a project-sourced
        duplicate is never re-emitted but never loses its board fields.
        """
        order: list[str] = []
        kept: dict[str, dict] = {}
        for doc in self._fetch_documents():
            doc_id = doc["id"]
            if doc_id not in kept:
                kept[doc_id] = doc
                order.append(doc_id)
                continue
            new_fields = doc.get("project_fields")
            if new_fields:
                merged = {**(kept[doc_id].get("project_fields") or {}), **new_fields}
                kept[doc_id] = {**kept[doc_id], "project_fields": merged}
        for doc_id in order:
            yield kept[doc_id]

    def _fetch_documents(self) -> list[dict]:
        """Run the GraphQL crawl once and cache it — `get_number_of_documents()`
        and `read_all_documents()` both call through here so the engine's
        count-then-read calling pattern doesn't crawl GitHub's API twice."""
        if self._cached_documents is None:
            self._cached_documents = asyncio.run(self._read_all_async())
        return self._cached_documents

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
            tasks = []
            for owner, name in self._repos:
                tasks.append(self._fetch_issues(client, semaphore, owner, name))
                if self._include_pull_requests:
                    tasks.append(
                        self._fetch_pull_requests(client, semaphore, owner, name)
                    )
            if self._project is not None:
                tasks.append(self._fetch_project_items(client, semaphore))
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

    def _issue_to_document(
        self, owner: str, name: str, node: dict, kind: str = "issue"
    ) -> dict:
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
            "kind": kind,
            "comments": comments,
            "project_fields": {},
        }

    def _graphql_states(self) -> list[str] | None:
        if self._state == "all":
            return None
        return [self._state.upper()]

    async def _fetch_pull_requests(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        owner: str,
        name: str,
    ) -> list[dict]:
        documents: list[dict] = []
        after: str | None = None
        states = self._graphql_pr_states()
        while True:
            data = await self._post_graphql(
                client,
                semaphore,
                queries.PULL_REQUESTS_QUERY,
                {
                    "owner": owner,
                    "name": name,
                    "first": self._page_size,
                    "after": after,
                    "states": states,
                    "labels": self._labels,
                },
            )
            prs = data["repository"]["pullRequests"]
            for node in prs["nodes"]:
                documents.append(
                    self._issue_to_document(owner, name, node, kind="pull_request")
                )
            page_info = prs["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            after = page_info["endCursor"]
        return documents

    def _graphql_pr_states(self) -> list[str] | None:
        if self._state == "all":
            return None
        if self._state == "open":
            return ["OPEN"]
        return ["CLOSED", "MERGED"]

    async def _fetch_project_items(
        self, client: httpx.AsyncClient, semaphore: asyncio.Semaphore
    ) -> list[dict]:
        assert self._project is not None
        login, number = self._project

        probe = await self._post_graphql(
            client,
            semaphore,
            queries.PROJECT_ITEMS_QUERY,
            {"login": login, "number": number, "first": 1, "after": None},
        )
        is_org = probe.get("organization") is not None
        query = (
            queries.PROJECT_ITEMS_QUERY if is_org else queries.PROJECT_ITEMS_QUERY_USER
        )
        root_key = "organization" if is_org else "user"

        documents: list[dict] = []
        after: str | None = None
        while True:
            data = await self._post_graphql(
                client,
                semaphore,
                query,
                {
                    "login": login,
                    "number": number,
                    "first": self._page_size,
                    "after": after,
                },
            )
            items = data[root_key]["projectV2"]["items"]
            for node in items["nodes"]:
                doc = self._project_item_to_document(node)
                if doc is not None:
                    documents.append(doc)
            page_info = items["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            after = page_info["endCursor"]
        return documents

    def _project_item_to_document(self, node: dict) -> dict | None:
        content = node.get("content")
        if content is None:
            return None
        field_values = self._extract_field_values(node)
        typename = content.get("__typename")

        if typename == "DraftIssue":
            return {
                "id": f"project:{node['id']}",
                "url": "",
                "modifiedTime": content.get("updatedAt") or content.get("createdAt"),
                "title": content.get("title") or "",
                "body": content.get("body") or "",
                "state": "DRAFT",
                "labels": [],
                "author": None,
                "kind": "draft",
                "comments": [],
                "project_fields": field_values,
            }

        owner = content["repository"]["owner"]["login"]
        name = content["repository"]["name"]
        kind = "pull_request" if typename == "PullRequest" else "issue"
        document = self._issue_to_document(owner, name, content, kind=kind)
        document["project_fields"] = field_values
        return document

    def _extract_field_values(self, node: dict) -> dict[str, str]:
        values: dict[str, str] = {}
        for fv in node.get("fieldValues", {}).get("nodes", []):
            name = fv.get("field", {}).get("name")
            if not name:
                continue
            value = fv.get("name") if fv.get("name") is not None else fv.get("text")
            if value is not None:
                values[name] = value
        return values

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
                if response.status_code == 429 or self._is_rate_limited_403(response):
                    last_error = GitHubGraphQLError(
                        response.status_code, "rate limited"
                    )
                    logger.warning(
                        f"GitHub GraphQL rate limited (HTTP {response.status_code}), "
                        f"retrying (attempt {attempt + 1}/{self._number_of_retries})"
                    )
                    await self._backoff(response, attempt)
                    continue
                if response.status_code == 403:
                    # A 403 without rate-limit headers is a permission/auth
                    # problem (insufficient token scope, SAML enforcement,
                    # repo access denied) — retrying it wastes attempts and
                    # would otherwise surface as a misleading "rate limited".
                    raise GitHubGraphQLError(
                        403,
                        "permission denied (insufficient token scope, SAML "
                        "enforcement, or repo access denied) — not a rate limit",
                    )
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

    @staticmethod
    def _is_rate_limited_403(response: httpx.Response) -> bool:
        """A 403 is a genuine rate limit only when GitHub's rate-limit
        headers say so — otherwise it's a permission/auth error (insufficient
        scope, SAML enforcement, repo access denied) that retrying can't fix."""
        if response.status_code != 403:
            return False
        if response.headers.get("X-RateLimit-Remaining") == "0":
            return True
        return bool(response.headers.get("Retry-After"))

    async def _backoff(self, response: httpx.Response, attempt: int) -> None:
        reset_header = response.headers.get("X-RateLimit-Reset")
        delay = self._retry_delay * (2**attempt)
        if reset_header:
            try:
                delay = max(float(reset_header) - time.time(), self._retry_delay)
            except ValueError:
                pass
        await asyncio.sleep(min(max(delay, 0.0), 60.0))
