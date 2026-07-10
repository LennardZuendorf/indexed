"""The four ``create`` subcommand shells.

Each shell only maps its own CLI options into ``cli_overrides`` and delegates to
the shared, schema-driven handler ``create._create``. The interface
(``indexed index create files|jira|confluence|outline``) is unchanged. These
shells reference none of the interactive-prompt seams the create tests patch, so
they live outside ``create.py`` and are re-exported from it via ``__getattr__``.
"""

from typing import Any, Dict

import typer

from . import _create_options as _opt
from .create import _create

app = typer.Typer(help="Create new collections")


@app.command("files", help="Create a new collection from local files or folders.")
def create_files(
    collection: _opt.CollectionFilesOpt = "files",
    path: _opt.PathOpt = None,
    include: _opt.IncludeOpt = None,
    exclude: _opt.ExcludeOpt = None,
    fail_fast: _opt.FailFastOpt = False,
    use_cache: _opt.UseCacheFilesOpt = True,
    force: _opt.ForceOpt = False,
    verbose: _opt.VerboseOpt = False,
    json_logs: _opt.JsonLogsOpt = False,
    log_level: _opt.LogLevelOpt = None,
    respect_gitignore: _opt.RespectGitignoreOpt = True,
    local: _opt.LocalOpt = False,
) -> None:
    """Create a Files collection with parameter resolution and progress tracking."""
    cli_overrides: Dict[str, Any] = {}
    if path:
        cli_overrides["path"] = path
    if include:
        cli_overrides["include_patterns"] = include
    if exclude:
        cli_overrides["exclude_patterns"] = exclude
    if fail_fast:
        cli_overrides["fail_fast"] = fail_fast
    cli_overrides["respect_gitignore"] = respect_gitignore

    _create(
        "files",
        collection=collection,
        url=None,
        cli_overrides=cli_overrides,
        use_cache=use_cache,
        force=force,
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        local=local,
    )


@app.command(
    "jira", help="Create a new collection from Jira issues using a base JQL query."
)
def create_jira(
    collection: _opt.CollectionJiraOpt = "jira",
    url: _opt.JiraUrlOpt = None,
    jql: _opt.JqlOpt = None,
    email: _opt.AtlassianEmailOpt = None,
    token: _opt.AtlassianTokenOpt = None,
    use_cache: _opt.UseCacheJiraOpt = True,
    force: _opt.ForceOpt = False,
    verbose: _opt.VerboseOpt = False,
    json_logs: _opt.JsonLogsOpt = False,
    log_level: _opt.LogLevelOpt = None,
    local: _opt.LocalOpt = False,
) -> None:
    """Create a Jira collection with parameter resolution and progress tracking."""
    cli_overrides: Dict[str, Any] = {}
    if jql:
        cli_overrides["query"] = jql
    if email:
        cli_overrides["email"] = email
    if token:
        cli_overrides["api_token"] = token

    _create(
        "jira",
        collection=collection,
        url=url,
        cli_overrides=cli_overrides,
        use_cache=use_cache,
        force=force,
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        local=local,
    )


@app.command(
    "confluence",
    help="Create a new collection from Confluence pages using a base CQL query.",
)
def create_confluence(
    collection: _opt.CollectionConfluenceOpt = "confluence",
    url: _opt.ConfluenceUrlOpt = None,
    cql: _opt.CqlOpt = None,
    email: _opt.AtlassianEmailOpt = None,
    token: _opt.AtlassianTokenOpt = None,
    read_all_comments: _opt.ReadAllCommentsOpt = True,
    use_cache: _opt.UseCacheConfluenceOpt = True,
    force: _opt.ForceOpt = False,
    verbose: _opt.VerboseOpt = False,
    json_logs: _opt.JsonLogsOpt = False,
    log_level: _opt.LogLevelOpt = None,
    local: _opt.LocalOpt = False,
) -> None:
    """Create a Confluence collection with parameter resolution and progress tracking."""
    cli_overrides: Dict[str, Any] = {}
    if cql:
        cli_overrides["query"] = cql
    if email:
        cli_overrides["email"] = email
    if token:
        cli_overrides["api_token"] = token
    cli_overrides["read_all_comments"] = read_all_comments

    _create(
        "confluence",
        collection=collection,
        url=url,
        cli_overrides=cli_overrides,
        use_cache=use_cache,
        force=force,
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        local=local,
    )


@app.command(
    "outline",
    help="Create a new collection from an Outline Wiki workspace (Cloud or self-hosted).",
)
def create_outline(
    collection: _opt.CollectionOutlineOpt = "outline",
    url: _opt.OutlineUrlOpt = None,
    token: _opt.OutlineTokenOpt = None,
    collection_id: _opt.CollectionIdOpt = None,
    include_attachments: _opt.IncludeAttachmentsOpt = True,
    ocr: _opt.OcrOpt = True,
    use_cache: _opt.UseCacheOutlineOpt = True,
    force: _opt.ForceOpt = False,
    verbose: _opt.VerboseOpt = False,
    json_logs: _opt.JsonLogsOpt = False,
    log_level: _opt.LogLevelOpt = None,
    local: _opt.LocalOpt = False,
) -> None:
    """Create an Outline Wiki collection (Cloud or any self-hosted deployment)."""
    cli_overrides: Dict[str, Any] = {}
    if token:
        cli_overrides["api_token"] = token
    if collection_id:
        cli_overrides["collection_ids"] = list(collection_id)
    cli_overrides["include_attachments"] = include_attachments
    cli_overrides["ocr_enabled"] = ocr

    _create(
        "outline",
        collection=collection,
        url=url,
        cli_overrides=cli_overrides,
        use_cache=use_cache,
        force=force,
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        local=local,
    )
