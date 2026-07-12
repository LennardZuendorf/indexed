"""Per-source specs that drive the schema-driven ``create`` subcommands.

The four ``create`` subcommands (files/jira/confluence/outline) are near-identical
clones that differ only in their fields, prompts, Cloud/Server detection, and
credential routing. This module captures those differences as *data* — one
:class:`SourceSpec` per source — so the command layer (``create.py``) can run one
shared handler instead of four hand-written copies.

Nothing here depends on the interactive-prompt seams patched by the create tests
(``console``/``print_error``/``is_credential_field``/…). Those live in
``create.py`` and read this module's pure data.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING
from pydantic import BaseModel
from urllib.parse import urlsplit

from loguru import logger

from ...utils.console import console

if TYPE_CHECKING:
    from indexed.core.v1.engine import SourceConfig


# --------------------------------------------------------------------------- #
# Cloud/Server detection + pre-setup verbose probe                            #
# --------------------------------------------------------------------------- #
def _is_cloud(url: str) -> bool:
    """Return True when an Atlassian base URL points at the cloud service.

    Strips whitespace and a trailing slash, then detects on the *parsed host*
    rather than a raw ``endswith`` on the whole URL string, so
    ``"https://x.atlassian.net/ "`` (trailing slash + whitespace) still routes to
    Cloud (foundation/6b bug E6).
    """
    normalized = url.strip().rstrip("/")
    host = urlsplit(normalized).hostname or ""
    return host.lower().endswith(".atlassian.net")


def _is_pre_setup_verbose(verbose: bool, log_level: Optional[str]) -> bool:
    """Return True when verbose/INFO/DEBUG output is requested.

    Use this at command-function top, before ``execute_create_command`` runs
    ``setup_root_logger``. ``is_verbose_mode()`` is unreliable there — it reads
    the global log level, which is not set yet (see .spec/lessons.md).
    """
    return verbose or (log_level or "").upper() in ("INFO", "DEBUG")


def _display_files_source_summary(present: Dict[str, Any]) -> None:
    """Print a concise Files source summary before the creation spinner starts."""
    from ...utils.components.info_row import create_info_row
    from ...utils.format import format_path_tilde
    from ...utils.files_source_display import build_excluded_row_text
    from indexed.connectors.files.schema import DEFAULT_EXCLUDED_DIRS

    path = str(present.get("path", ""))
    respect_gitignore: bool = present.get("respect_gitignore", True)
    _dirs = present.get("excluded_dirs")
    excluded_dirs: list[str] = (
        _dirs if isinstance(_dirs, list) else list(DEFAULT_EXCLUDED_DIRS)
    )
    _patterns = present.get("include_patterns")
    include_patterns: list[str] = _patterns if isinstance(_patterns, list) else ["*"]

    console.print(create_info_row("Path", format_path_tilde(path)))
    console.print(
        create_info_row(
            "Excluded",
            build_excluded_row_text(
                path, include_patterns, excluded_dirs, respect_gitignore
            ),
        )
    )
    console.print()


# --------------------------------------------------------------------------- #
# Lazy connector-schema loaders (keep heavy connector imports off startup)     #
# --------------------------------------------------------------------------- #
def _load(module: str, name: str) -> Any:
    return getattr(importlib.import_module(module), name)


def _load_config(module: str, name: str) -> Type[BaseModel]:
    cls = _load(module, name)
    assert isinstance(cls, type)
    return cls


def _files_config() -> Type[BaseModel]:
    return _load_config("indexed.connectors.files.schema", "LocalFilesConfig")


def _jira_cloud_config() -> Type[BaseModel]:
    return _load_config("indexed.connectors.jira.schema", "JiraCloudConfig")


def _jira_config() -> Type[BaseModel]:
    return _load_config("indexed.connectors.jira.schema", "JiraConfig")


def _confluence_cloud_config() -> Type[BaseModel]:
    return _load_config("indexed.connectors.confluence.schema", "ConfluenceCloudConfig")


def _confluence_config() -> Type[BaseModel]:
    return _load_config("indexed.connectors.confluence.schema", "ConfluenceConfig")


def _outline_config() -> Type[BaseModel]:
    return _load_config("indexed.connectors.outline.schema", "OutlineConfig")


def _outline_cloud_url() -> str:
    return str(_load("indexed.connectors.outline.schema", "OUTLINE_CLOUD_URL"))


# --------------------------------------------------------------------------- #
# Field prompt specs (per-field: prompt text + pure parser)                    #
# --------------------------------------------------------------------------- #
def _parse_path(raw: str) -> str:
    # Rejects empty/whitespace (raises ValueError) and normalizes expanduser +
    # resolve so the stored path is absolute (foundation/6b bugs E5/E7).
    from indexed.connectors.files.files_document_reader import normalize_base_path

    return normalize_base_path(raw)


def _parse_csv(raw: str, default: List[str]) -> List[str]:
    return [p.strip() for p in raw.split(",")] if raw else list(default)


def _parse_bool(raw: str) -> bool:
    return raw.lower() in ("yes", "y", "true")


def _parse_query(raw: str, default: str) -> str:
    return raw or default


@dataclass(frozen=True)
class FieldSpec:
    """How to prompt for one connector field and parse the raw input."""

    label: str
    suffix: str = ""
    parse: Callable[[str], Any] = lambda raw: raw
    error: str = "Value is required"


_FILES_FIELDS: Dict[str, FieldSpec] = {
    "path": FieldSpec(
        "Path to files or directory", parse=_parse_path, error="Path is required"
    ),
    "include_patterns": FieldSpec(
        "Include patterns (comma-separated)",
        " [*]",
        partial(_parse_csv, default=["*"]),
    ),
    "exclude_patterns": FieldSpec(
        "Exclude patterns (comma-separated)",
        " []",
        partial(_parse_csv, default=[]),
    ),
    "fail_fast": FieldSpec("Stop on first error? (yes/no)", " [no]", _parse_bool),
}

_JIRA_QUERY = FieldSpec(
    "JQL query", " [project = PROJ]", partial(_parse_query, default="project = PROJ")
)
_CONFLUENCE_QUERY = FieldSpec(
    "CQL query", " [type=page]", partial(_parse_query, default="type=page")
)


# --------------------------------------------------------------------------- #
# reader_opts builders + verbose-mode pre-creation loggers                     #
# --------------------------------------------------------------------------- #
def _files_reader_opts(present: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "includePatterns": present.get("include_patterns", ["*"]),
        "excludePatterns": present.get("exclude_patterns", []),
        "failFast": present.get("fail_fast", False),
        "respectGitignore": present.get("respect_gitignore", True),
    }


def _jira_reader_opts(present: Dict[str, Any]) -> Dict[str, Any]:
    return {}  # Credentials are read from ConfigService by the connector.


def _confluence_reader_opts(present: Dict[str, Any]) -> Dict[str, Any]:
    return {"readAllComments": present.get("read_all_comments", True)}


def _outline_reader_opts(present: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "collectionIds": present.get("collection_ids"),
        "includeAttachments": present.get("include_attachments", True),
        "ocrEnabled": present.get("ocr_enabled", True),
    }


def _jira_verbose_log(present: Dict[str, Any]) -> None:
    logger.info("Connecting to Jira at %s...", present["url"])
    logger.info("Using JQL query: %s", present["query"])


def _confluence_verbose_log(present: Dict[str, Any]) -> None:
    logger.info("Connecting to Confluence at %s...", present["url"])
    logger.info("Using CQL query: %s", present["query"])


def _outline_verbose_log(present: Dict[str, Any]) -> None:
    url = present["url"]
    deployment = "Cloud" if url == _outline_cloud_url() else "self-hosted"
    logger.info("Connecting to Outline at %s (%s)...", url, deployment)


# --------------------------------------------------------------------------- #
# Source spec                                                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceSpec:
    """Everything that differs between the four ``create`` subcommands."""

    key: str
    namespace: str
    display_name: str
    success_suffix: str
    source_path_key: str
    fields_by_name: Dict[str, FieldSpec]
    reader_opts: Callable[[Dict[str, Any]], Dict[str, Any]]
    # source-type resolution -------------------------------------------------
    default_source_type: str = ""
    default_config: Optional[Callable[[], Type[BaseModel]]] = None
    cloud_detection: bool = False
    cloud_source_type: str = ""
    server_source_type: str = ""
    cloud_config: Optional[Callable[[], Type[BaseModel]]] = None
    server_config: Optional[Callable[[], Type[BaseModel]]] = None
    # url phase --------------------------------------------------------------
    has_url: bool = False
    url_label: str = ""
    url_default_fn: Optional[Callable[[], str]] = None
    # server credential check injected into the missing-field loop ----------
    server_auth: bool = False
    server_env: tuple[str, ...] = ()
    # presentation -----------------------------------------------------------
    verbose_log: Optional[Callable[[Dict[str, Any]], None]] = None
    pre_display: Optional[Callable[[Dict[str, Any]], None]] = None
    progress_uses_url: bool = False
    has_query: bool = False

    @property
    def url_excludes(self) -> tuple[str, ...]:
        """Fields resolved before the missing-field loop (url is handled first)."""
        return ("url",) if self.has_url else ()


SOURCE_SPECS: Dict[str, SourceSpec] = {
    "files": SourceSpec(
        key="files",
        namespace="sources.files",
        display_name="Files",
        success_suffix="from files",
        source_path_key="path",
        fields_by_name=_FILES_FIELDS,
        reader_opts=_files_reader_opts,
        default_source_type="localFiles",
        default_config=_files_config,
        pre_display=_display_files_source_summary,
    ),
    "jira": SourceSpec(
        key="jira",
        namespace="sources.jira",
        display_name="Jira",
        success_suffix="from Jira",
        source_path_key="url",
        fields_by_name={"query": _JIRA_QUERY, "jql": _JIRA_QUERY},
        reader_opts=_jira_reader_opts,
        cloud_detection=True,
        cloud_source_type="jiraCloud",
        server_source_type="jira",
        cloud_config=_jira_cloud_config,
        server_config=_jira_config,
        has_url=True,
        url_label="Jira URL",
        verbose_log=_jira_verbose_log,
        progress_uses_url=True,
        has_query=True,
    ),
    "confluence": SourceSpec(
        key="confluence",
        namespace="sources.confluence",
        display_name="Confluence",
        success_suffix="from Confluence",
        source_path_key="url",
        fields_by_name={"query": _CONFLUENCE_QUERY, "cql": _CONFLUENCE_QUERY},
        reader_opts=_confluence_reader_opts,
        cloud_detection=True,
        cloud_source_type="confluenceCloud",
        server_source_type="confluence",
        cloud_config=_confluence_cloud_config,
        server_config=_confluence_config,
        has_url=True,
        url_label="Confluence URL",
        server_auth=True,
        server_env=("CONF_TOKEN", "CONF_LOGIN", "CONF_PASSWORD"),
        verbose_log=_confluence_verbose_log,
        progress_uses_url=True,
        has_query=True,
    ),
    "outline": SourceSpec(
        key="outline",
        namespace="sources.outline",
        display_name="Outline",
        success_suffix="from Outline",
        source_path_key="url",
        fields_by_name={},
        reader_opts=_outline_reader_opts,
        default_source_type="outline",
        default_config=_outline_config,
        has_url=True,
        url_label="Outline URL",
        url_default_fn=_outline_cloud_url,
        verbose_log=_outline_verbose_log,
        progress_uses_url=True,
    ),
}


def resolve_source(spec: SourceSpec, url: Optional[str]) -> tuple[str, Type[BaseModel]]:
    """Resolve ``(source_type, config_class)`` from the spec and the resolved URL.

    Sources with ``cloud_detection`` pick Cloud vs Server from the URL host
    (``*.atlassian.net`` → Cloud); the rest use a fixed source type.
    """
    if spec.cloud_detection:
        assert spec.cloud_config is not None and spec.server_config is not None
        if _is_cloud(url or ""):
            return spec.cloud_source_type, spec.cloud_config()
        return spec.server_source_type, spec.server_config()
    assert spec.default_config is not None
    return spec.default_source_type, spec.default_config()


def make_build_source_config(
    spec: SourceSpec, source_type: str
) -> Callable[[Dict[str, Any], str], "SourceConfig"]:
    """Return a ``build_source_config`` callback bound to one source spec."""

    def build(present: Dict[str, Any], coll_name: str) -> "SourceConfig":
        # Resolve SourceConfig/DEFAULT_INDEXER through the create module's lazy
        # facade so tests can patch them at the core seam.
        from indexed.cli.knowledge.commands import create as this_module

        kwargs: Dict[str, Any] = {
            "name": coll_name,
            "type": source_type,
            "base_url_or_path": present[spec.source_path_key],
            "indexer": this_module.DEFAULT_INDEXER,
            "reader_opts": spec.reader_opts(present),
        }
        if spec.has_query:
            kwargs["query"] = present["query"]
        return this_module.SourceConfig(**kwargs)

    return build
