"""Annotated typer option aliases for the ``create`` subcommands.

Factoring the per-option ``typer.Option`` metadata into reusable ``Annotated``
aliases keeps the four command signatures in ``_create_commands.py`` to one line
per parameter while preserving the exact flags, help text, and help panels.
"""

from typing import Annotated, List, Optional

import typer

_LOG = "Logging"
_STORE = "Storage"

# Shared across every source (identical help text) -------------------------- #
ForceOpt = Annotated[
    bool,
    typer.Option(
        "--force",
        help="Delete any existing collection with the same name before creating a new one.",
    ),
]
VerboseOpt = Annotated[
    bool,
    typer.Option(
        "--verbose",
        "-v",
        help="Enable verbose (INFO) logging",
        rich_help_panel=_LOG,
    ),
]
JsonLogsOpt = Annotated[
    bool,
    typer.Option(
        "--json-logs",
        help="Output logs as JSON (structured)",
        rich_help_panel=_LOG,
    ),
]
LogLevelOpt = Annotated[
    Optional[str],
    typer.Option(
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        rich_help_panel=_LOG,
    ),
]
LocalOpt = Annotated[
    bool,
    typer.Option(
        "--local",
        help="Save the collection to .indexed/ in the current directory instead of ~/.indexed/",
        rich_help_panel=_STORE,
    ),
]
EngineOpt = Annotated[
    Optional[str],
    typer.Option(
        "--engine",
        help="Engine for this NEW collection: v1 or v2 (default: v1)",
        rich_help_panel=_STORE,
    ),
]
# Group-level twin for the ``create`` callback (``index create --engine v2
# files ...``). Same flag and wording as ``EngineOpt``; no help panel, so
# ``index create --help`` lists it in the main Options block — the group has no
# other Storage options for a panel to hold.
GroupEngineOpt = Annotated[
    Optional[str],
    typer.Option(
        "--engine",
        help="Engine for this NEW collection: v1 or v2 (default: v1)",
    ),
]

# Files --------------------------------------------------------------------- #
CollectionFilesOpt = Annotated[
    str,
    typer.Option(
        "--collection",
        "-c",
        help="Name of the collection (default: files).",
    ),
]
PathOpt = Annotated[
    Optional[str],
    typer.Option(
        "--path",
        "-p",
        help="Path to the root directory or file(s) (from config or prompt if not provided).",
    ),
]
IncludeOpt = Annotated[
    Optional[List[str]],
    typer.Option(
        "--include",
        help="List of regex patterns for files/directories to include (can be specified multiple times).",
        show_default=False,
    ),
]
ExcludeOpt = Annotated[
    Optional[List[str]],
    typer.Option(
        "--exclude",
        help="List of regex patterns for files/directories to exclude (can be specified multiple times).",
        show_default=False,
    ),
]
FailFastOpt = Annotated[
    bool,
    typer.Option(
        "--fail-fast/--no-fail-fast",
        help="Stop and abort if the first file read error occurs.",
    ),
]
UseCacheFilesOpt = Annotated[
    bool,
    typer.Option(
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged content.",
    ),
]
RespectGitignoreOpt = Annotated[
    Optional[bool],
    typer.Option(
        "--respect-gitignore/--no-respect-gitignore",
        help="Respect .gitignore files and skip noise directories (node_modules, .venv, etc.).",
    ),
]

# Jira ---------------------------------------------------------------------- #
CollectionJiraOpt = Annotated[
    str,
    typer.Option(
        "--collection",
        "-c",
        help="Name of the collection (default: jira).",
    ),
]
JiraUrlOpt = Annotated[
    Optional[str],
    typer.Option(
        "--url",
        "-u",
        help="Base URL of the Jira instance (from config or prompt if not provided).",
    ),
]
JqlOpt = Annotated[
    Optional[str],
    typer.Option(
        "--jql",
        "--query",
        "-q",
        help="JQL query (from config or prompt if not provided).",
    ),
]
AtlassianEmailOpt = Annotated[
    Optional[str],
    typer.Option(
        "--email",
        help="Atlassian account email (overrides config/env).",
    ),
]
AtlassianTokenOpt = Annotated[
    Optional[str],
    typer.Option(
        "--token",
        help="Atlassian API token (overrides env ATLASSIAN_TOKEN).",
    ),
]
UseCacheJiraOpt = Annotated[
    bool,
    typer.Option(
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged issues.",
    ),
]

# Confluence ---------------------------------------------------------------- #
CollectionConfluenceOpt = Annotated[
    str,
    typer.Option(
        "--collection",
        "-c",
        help="Name of the collection (default: confluence).",
    ),
]
ConfluenceUrlOpt = Annotated[
    Optional[str],
    typer.Option(
        "--url",
        "-u",
        help="Base URL of the Confluence instance (from config or prompt if not provided).",
    ),
]
CqlOpt = Annotated[
    Optional[str],
    typer.Option(
        "--cql",
        "--query",
        "-q",
        help="CQL query (from config or prompt if not provided).",
    ),
]
ReadAllCommentsOpt = Annotated[
    Optional[bool],
    typer.Option(
        "--read-all-comments/--first-level-comments",
        help="Read all nested comments if enabled, otherwise include only first-level comments.",
    ),
]
UseCacheConfluenceOpt = Annotated[
    bool,
    typer.Option(
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged pages.",
    ),
]

# Outline ------------------------------------------------------------------- #
CollectionOutlineOpt = Annotated[
    str,
    typer.Option(
        "--collection",
        "-c",
        help="Name of the collection (default: outline).",
    ),
]
OutlineUrlOpt = Annotated[
    Optional[str],
    typer.Option(
        "--url",
        "-u",
        help="Outline base URL. Defaults to https://app.getoutline.com (Cloud). Provide your own domain for self-hosted Outline.",
    ),
]
OutlineTokenOpt = Annotated[
    Optional[str],
    typer.Option(
        "--token",
        help="Outline API token (overrides env OUTLINE_API_TOKEN).",
    ),
]
CollectionIdOpt = Annotated[
    Optional[List[str]],
    typer.Option(
        "--collection-id",
        help="Restrict to specific Outline collection IDs (can be specified multiple times). Defaults to all collections.",
        show_default=False,
    ),
]
IncludeAttachmentsOpt = Annotated[
    Optional[bool],
    typer.Option(
        "--include-attachments/--no-include-attachments",
        help="Download and OCR inline images and file attachments.",
    ),
]
OcrOpt = Annotated[
    Optional[bool],
    typer.Option(
        "--ocr/--no-ocr",
        help="Enable OCR for image attachments.",
    ),
]
UseCacheOutlineOpt = Annotated[
    bool,
    typer.Option(
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged documents.",
    ),
]
