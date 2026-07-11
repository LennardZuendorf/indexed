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

from tests.fixtures.connectors import payloads, stub_routes  # noqa: E402


def main() -> None:
    from pytest_httpserver import HTTPServer

    httpserver = HTTPServer(host="127.0.0.1", port=0)
    httpserver.start()

    try:
        stub_routes.register_jira_server(
            httpserver,
            search_payload=payloads.jira_server_search(),
        )
        stub_routes.register_confluence_server(
            httpserver,
            search_payload=payloads.confluence_server_search(),
        )
        stub_routes.register_outline(
            httpserver,
            documents_list=payloads.outline_documents_list(),
            document_info=payloads.outline_document_info(),
        )

        base_url = httpserver.url_for("").rstrip("/")

        print(f"Stub server running at: {base_url}")
        print()
        print("Auth env vars (any non-empty value works against the stub):")
        print("  export JIRA_TOKEN=stub-token")
        print("  export CONF_TOKEN=stub-token")
        print("  export OUTLINE_API_TOKEN=stub-token")
        print()
        print("Copy-paste commands:")
        print()
        print("# Jira Server")
        print(
            f"  uv run indexed index create jira --collection jira-e2e --url {base_url} "
            f'--jql "project = SRV" --no-cache --force'
        )
        print()
        print("# Confluence Server")
        print(
            f"  uv run indexed index create confluence --collection conf-e2e --url {base_url} "
            f'--cql "type=page" --first-level-comments --no-cache --force'
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
