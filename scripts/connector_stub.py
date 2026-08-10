"""Standalone localhost stub server for manual connector testing.

Starts a ``pytest_httpserver.HTTPServer`` and registers the same Jira
Server / Confluence Server / Outline routes used by the automated E2E
tests (see ``tests/fixtures/connectors/stub_routes.py``), then prints
ready-to-paste ``indexed index create`` commands for each connector and
blocks until interrupted.

Usage::

    /opt/homebrew/bin/uv run python scripts/connector_stub.py

Then in another shell, export the auth env vars it prints and run the
printed ``indexed index create ...`` commands against the running stub.

Ctrl-C to stop the server.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repo-root "tests" package importable when this script is run
# directly (not via `uv run pytest`), e.g. `uv run python scripts/connector_stub.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.fixtures.connectors import payloads, stub_routes

# The stub now checks the Authorization header on every request (it used to
# accept any/no auth) -- this is the one token that satisfies all three
# registrars below, and the only value that will work against the running
# stub.
_STUB_TOKEN = "stub-token"


def main() -> None:
    from pytest_httpserver import HTTPServer

    httpserver = HTTPServer(host="127.0.0.1", port=0)
    httpserver.start()

    try:
        stub_routes.register_jira_server(
            httpserver,
            issues=[payloads.jira_server_issue()],
            expected_token=_STUB_TOKEN,
        )
        # comment_count=1 + comments_by_page_id exercises the *default*
        # read_all_comments=True reader path (a separate paginated request
        # to /child/comment), not just the --first-level-comments mode.
        page = payloads.confluence_server_page(comment_count=1)
        stub_routes.register_confluence_server(
            httpserver,
            pages=[page],
            expected_token=_STUB_TOKEN,
            comments_by_page_id={
                page["id"]: [
                    payloads.confluence_comment(
                        "<p>Ping the on-call engineer if this breaks again.</p>"
                    )
                ]
            },
        )
        stub_routes.register_outline(
            httpserver,
            documents=[payloads.outline_document_info()],
            expected_token=_STUB_TOKEN,
        )

        base_url = httpserver.url_for("").rstrip("/")

        print(f"Stub server running at: {base_url}")
        print()
        print(f"Auth env vars (must be exactly '{_STUB_TOKEN}' -- the stub now")
        print("rejects any other value, or a missing header, with 401):")
        print(f"  export JIRA_TOKEN={_STUB_TOKEN}")
        print(f"  export CONF_TOKEN={_STUB_TOKEN}")
        print(f"  export OUTLINE_API_TOKEN={_STUB_TOKEN}")
        print()
        print("Copy-paste commands:")
        print()
        print("# Jira Server")
        print(
            f"  uv run indexed index create jira --collection jira-e2e --url {base_url} "
            f'--jql "project = SRV" --no-cache --force'
        )
        print()
        print("# Confluence Server (default read_all_comments=True)")
        print(
            f"  uv run indexed index create confluence --collection conf-e2e --url {base_url} "
            f'--cql "type=page" --no-cache --force'
        )
        print()
        print("# Outline")
        print(
            f"  uv run indexed index create outline --collection ol-e2e --url {base_url} "
            f"--collection-id col1 --no-include-attachments --no-ocr --no-cache --force"
        )
        print()
        print("Then search, e.g.:")
        print(
            '  uv run indexed index search "database timeout on staging" --collection jira-e2e'
        )
        print()
        print("Press Ctrl-C to stop the stub server.")

        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
    finally:
        httpserver.stop()
        print("Stub server stopped.")


if __name__ == "__main__":
    main()
