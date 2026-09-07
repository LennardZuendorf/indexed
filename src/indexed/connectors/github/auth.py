"""Token resolution for the GitHub connector: explicit config/env -> `gh auth token` -> error."""

from __future__ import annotations

import os
import subprocess

from indexed.config import ConfigurationError

# Defined here rather than in `schema.py` because `schema` imports this module —
# a back-import would be circular. `schema` re-exports it as the public name.
GITHUB_CLOUD_HOST = "github.com"

_GH_TOKEN_ENV = "GITHUB_TOKEN"
_GH_AUTH_TIMEOUT_SECONDS = 5


def resolve_token(explicit: str | None, host: str | None = None) -> str:
    """Resolve a GitHub access token.

    Priority: `explicit` (config/.env, already resolved by ConfigService) ->
    the plain `GITHUB_TOKEN` env var -> `gh auth token` (local GitHub CLI) ->
    raise ConfigurationError.

    `host` scopes the `gh` CLI lookup so an Enterprise collection gets that
    host's token instead of github.com's.
    """
    if explicit:
        return explicit

    env_token = os.getenv(_GH_TOKEN_ENV)
    if env_token:
        return env_token

    gh_token = _gh_cli_token(host)
    if gh_token:
        return gh_token

    raise ConfigurationError(
        "No GitHub token found. Set INDEXED__sources__github__token (or "
        f"{_GH_TOKEN_ENV}) in your .env file, or run `gh auth login`."
    )


def _gh_cli_token(host: str | None = None) -> str | None:
    command = ["gh", "auth", "token"]
    if host and host != GITHUB_CLOUD_HOST:
        command += ["--hostname", host]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_GH_AUTH_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None

    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None
