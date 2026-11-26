"""Async GraphQL v4 reader for GitHub issues, pull requests, and Projects v2 boards."""

from __future__ import annotations

import asyncio
import time
from typing import Iterator

import httpx
from loguru import logger

from . import queries

# Comment evidence budget. A thread page embeds its first 100 comments; each
# further page is one follow-up request, so a document costs at most
# MAX_COMMENT_PAGES comment pages (1000 comments). Past that the document is
# marked `commentsTruncated` with the limit applied — never left silent.
COMMENT_PAGE_SIZE = 100
MAX_COMMENT_PAGES = 10


class GitHubGraphQLError(Exception):
    """Raised when the GitHub GraphQL API returns an error response."""

    def __init__(
        self, status_code: int, message: str, errors: list[dict] | None = None
    ) -> None:
        super().__init__(f"GitHub GraphQL error ({status_code}): {message}")
        self.status_code = status_code
        self.message = message
        # Raw GraphQL `errors` entries, so callers can branch on their `type`/
        # `path` (see `_is_organization_not_found`) instead of parsing `message`.
        self.errors = errors


def _is_organization_not_found(error: GitHubGraphQLError) -> bool:
    """True when GitHub answered an org probe with "no such organization".

    A user-owned Projects v2 board answers the `organization(login:)` probe with
    BOTH `data.organization: null` AND a NOT_FOUND error, so the null alone is
    never reached — this recognizes that shape as "not an org, try the user
    query" rather than a hard failure.
    """
    return any(
        entry.get("type") == "NOT_FOUND" and entry.get("path") == ["organization"]
        for entry in (error.errors or [])
    )


def _is_node_not_found(error: GitHubGraphQLError) -> bool:
    """True when a follow-up `node(id:)` probe answered "no such node".

    A thread deleted between its list page and its comment page comes back as
    `data.node: null` plus a NOT_FOUND error at `path=["node"]`; that is
    truncation to report, not a reason to abort the crawl.
    """
    return any(
        entry.get("type") == "NOT_FOUND" and entry.get("path") == ["node"]
        for entry in (error.errors or [])
    )


class GitHubGraphQLReader:
    """Reads issues, pull requests, and Projects v2 boards from GitHub via the
    GraphQL v4 API.

    Pages each repo's issues and pull requests sequentially via cursor
    pagination, with requests bounded by a semaphore and retried with backoff
    on rate limiting.

    Args:
        graphql_url: GraphQL endpoint (Cloud or Enterprise).
        token: Bearer token for authentication.
        host: Configured GitHub host, persisted so an incremental update
            rebuilds against the same deployment.
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
        host: str,
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
        self._host = host
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
        # Counts the deduplicated set, so it matches what read_all_documents()
        # yields when repos and a project board overlap.
        return len(self._deduplicated_documents())

    def read_all_documents(self) -> Iterator[dict]:
        yield from self._deduplicated_documents()

    def _deduplicated_documents(self) -> list[dict]:
        """Raw issue documents across all configured repos, deduplicated by id.

        Deduplication happens inside the crawl (`_merge_documents`, before
        comment pagination), so a document reachable via more than one source
        (e.g. a repo scan and a project board) is kept once, carrying the union
        of every copy's project_fields — non-empty values win, later copies take
        precedence on overlapping field names — and fetches its remaining
        comment pages once, not once per source.
        """
        return self._fetch_documents()

    @staticmethod
    def _merge_documents(documents: list[dict]) -> list[dict]:
        order: list[str] = []
        kept: dict[str, dict] = {}
        for doc in documents:
            doc_id = doc["id"]
            if doc_id not in kept:
                kept[doc_id] = doc
                order.append(doc_id)
                continue
            new_fields = doc.get("project_fields")
            primary = kept[doc_id]
            merged = {**primary}
            if new_fields:
                merged["project_fields"] = {
                    **(primary.get("project_fields") or {}),
                    **new_fields,
                }
            # Keep the comment continuation key from whichever copy has one.
            for key in ("_nodeId", "_commentsCursor"):
                if key not in merged and doc.get(key):
                    merged[key] = doc[key]
            kept[doc_id] = merged
        return [kept[doc_id] for doc_id in order]

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
            "host": self._host,
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
            # Dedupe before comment pagination: a thread reachable from both a
            # repo scan and a project board must fetch its remaining comment
            # pages once, not once per source.
            merged = self._merge_documents(documents)
            return await self._complete_comment_pages(client, semaphore, merged)

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
        query = (
            queries.ISSUES_QUERY
            if self._include_comments
            else queries.ISSUES_QUERY_NO_COMMENTS
        )
        while True:
            data = await self._post_graphql(
                client,
                semaphore,
                query,
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
        document = {
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
            "comments": [],
            "project_fields": {},
        }
        if self._include_comments:
            connection = node.get("comments") or {}
            document["comments"] = [
                self._comment_to_dict(c) for c in connection.get("nodes") or []
            ]
            page_info = connection.get("pageInfo") or {}
            if page_info.get("hasNextPage"):
                document["_nodeId"] = node.get("id")
                document["_commentsCursor"] = page_info.get("endCursor")
        return document

    @staticmethod
    def _comment_to_dict(comment: dict) -> dict:
        return {
            "id": comment.get("id"),
            "url": comment.get("url"),
            "author": comment["author"]["login"] if comment.get("author") else None,
            "body": comment.get("body") or "",
        }

    async def _complete_comment_pages(
        self,
        client: "httpx.AsyncClient",
        semaphore: asyncio.Semaphore,
        documents: list[dict],
    ) -> list[dict]:
        """Follow the comment cursor past the first embedded page.

        One request per extra page, capped at MAX_COMMENT_PAGES pages per
        document; duplicates are skipped by comment id so an overlapping page
        can never double-index a comment. A document still truncated at the cap
        carries `commentsTruncated` and `commentsLimit` rather than looking
        complete.
        """
        for document in documents:
            cursor = document.pop("_commentsCursor", None)
            node_id = document.pop("_nodeId", None)
            if not cursor or not node_id:
                continue
            seen = {comment.get("id") for comment in document["comments"]}
            pages = 1
            has_next = True
            while has_next and pages < MAX_COMMENT_PAGES:
                try:
                    data = await self._post_graphql(
                        client,
                        semaphore,
                        queries.COMMENT_PAGE_QUERY,
                        {"id": node_id, "first": COMMENT_PAGE_SIZE, "after": cursor},
                    )
                except GitHubGraphQLError as exc:
                    if not _is_node_not_found(exc):
                        raise
                    # The thread vanished mid-crawl: keep what was collected and
                    # let the truncation branch below report incomplete coverage.
                    break
                connection = (data.get("node") or {}).get("comments")
                if connection is None:
                    break
                for comment in connection.get("nodes") or []:
                    comment_id = comment.get("id")
                    if comment_id in seen:
                        continue
                    seen.add(comment_id)
                    document["comments"].append(self._comment_to_dict(comment))
                page_info = connection.get("pageInfo") or {}
                has_next = bool(page_info.get("hasNextPage"))
                cursor = page_info.get("endCursor")
                pages += 1
            if has_next:
                document["commentsTruncated"] = True
                document["commentsLimit"] = pages * COMMENT_PAGE_SIZE
                logger.warning(
                    f"GitHub: {document['id']} has more comments than the "
                    f"{pages * COMMENT_PAGE_SIZE}-comment cap; indexing the "
                    "first pages and marking the thread truncated"
                )
        return documents

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
        query = (
            queries.PULL_REQUESTS_QUERY
            if self._include_comments
            else queries.PULL_REQUESTS_QUERY_NO_COMMENTS
        )
        while True:
            data = await self._post_graphql(
                client,
                semaphore,
                query,
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

        try:
            probe = await self._post_graphql(
                client,
                semaphore,
                queries.PROJECT_ITEMS_QUERY,
                {"login": login, "number": number, "first": 1, "after": None},
            )
        except GitHubGraphQLError as exc:
            if not _is_organization_not_found(exc):
                raise
            probe = {"organization": None}
        is_org = probe.get("organization") is not None
        if self._include_comments:
            query = (
                queries.PROJECT_ITEMS_QUERY
                if is_org
                else queries.PROJECT_ITEMS_QUERY_USER
            )
        else:
            query = (
                queries.PROJECT_ITEMS_QUERY_NO_COMMENTS
                if is_org
                else queries.PROJECT_ITEMS_QUERY_USER_NO_COMMENTS
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
            project_data = (data.get(root_key) or {}).get("projectV2")
            if project_data is None:
                raise GitHubGraphQLError(
                    404,
                    f"Projects v2 board {login}/{number} was not found or is not "
                    "accessible with the configured token.",
                )
            items = project_data["items"]
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
                if response.status_code >= 500:
                    # A transient upstream error shouldn't abort the whole
                    # crawl — retry it the same way as a rate limit.
                    last_error = GitHubGraphQLError(
                        response.status_code, "server error"
                    )
                    logger.warning(
                        f"GitHub GraphQL server error (HTTP {response.status_code}), "
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
                    raise GitHubGraphQLError(
                        response.status_code, str(errors), errors=errors
                    )
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
        # The final attempt raises regardless, so sleeping first (up to 60s)
        # only adds latency.
        if attempt >= self._number_of_retries - 1:
            return
        reset_header = response.headers.get("X-RateLimit-Reset")
        delay = self._retry_delay * (2**attempt)
        if reset_header:
            try:
                delay = max(float(reset_header) - time.time(), self._retry_delay)
            except ValueError:
                pass
        await asyncio.sleep(min(max(delay, 0.0), 60.0))
