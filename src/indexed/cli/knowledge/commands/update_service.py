"""Orchestration service for the update command (thin command, fat service).

``update.py`` parses args and renders; the multi-collection work lives here:
resolving which collections to refresh, capturing before-state, running the
per-collection update loop, and collecting per-collection failures.

Foundation E8 is the load-bearing behavior: the loop attempts *every*
collection even when one fails, collects the failures, and lets the command
exit non-zero — a single bad collection can't abort the rest or masquerade as
a silent success.

The loop reaches its rendering + service seams through the ``cmd`` module
handle (the ``update`` command module) rather than importing them directly, so
the command module stays the single place tests patch (``console``,
``print_error``, ``update_service``, ``inspect``, …) and the lazy service
loaders resolve exactly as they do for the command itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import typer
from rich.markup import escape
from rich.text import Text

from ...utils.components import create_detail_card, print_success
from ...utils.components.theme import (
    get_dim_style,
    get_error_style,
    get_heading_style,
    get_success_style,
)
from ...utils.console import console
from ...utils.format import format_source_type
from ...utils.simple_output import print_json


def _read_manifest_reader_config(collection_name: str, collections_path: str) -> dict:
    """Read the reader dict from a collection manifest; return {} on failure."""
    try:
        import json
        from pathlib import Path

        manifest_path = Path(collections_path) / collection_name / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return manifest.get("reader", {})
    except Exception:
        pass
    return {}


def _display_collection_update_header(
    coll_name: str,
    source_type: str | None,
    reader_config: dict,
    *,
    console: Any = console,
) -> None:
    """Print the per-collection heading block before progress bars.

    ``console`` is injected by ``run_update_loop`` (as ``cmd.console``) so tests
    patching ``update.console`` capture the header prints too; it defaults to the
    shared console for direct use.
    """
    from indexed.connectors.files.schema import DEFAULT_EXCLUDED_DIRS

    from ...utils.components.info_row import create_info_row
    from ...utils.files_source_display import build_excluded_row_text
    from ...utils.format import format_path_tilde

    heading = get_heading_style()
    # coll_name is user-controlled (the collection name argument) — escape
    # before it enters this markup string; the surrounding tags are ours.
    console.print(f'\n[{heading}]Updating Collection "{escape(coll_name)}"[/{heading}]')

    if source_type:
        console.print(create_info_row("Type", format_source_type(source_type)))

    if source_type == "localFiles" and reader_config:
        path = str(reader_config.get("basePath", ""))
        console.print(create_info_row("Path", format_path_tilde(path)))

        include_patterns: list[str] = reader_config.get("includePatterns") or ["*"]
        positive = [p for p in include_patterns if not p.startswith("!")]
        patterns_display = "* (all files)" if positive == ["*"] else ", ".join(positive)
        console.print(create_info_row("Included Patterns", patterns_display))

        _dirs = reader_config.get("excludedDirs")
        excluded_dirs: list[str] = (
            _dirs if isinstance(_dirs, list) else list(DEFAULT_EXCLUDED_DIRS)
        )
        respect_gitignore: bool = reader_config.get("respectGitignore", True)
        console.print(
            create_info_row(
                "Excluded",
                build_excluded_row_text(
                    path, include_patterns, excluded_dirs, respect_gitignore
                ),
            )
        )

    console.print()


def format_update_comparison(
    before: Any, after: Any, *, console: Any = console
) -> None:
    """
    Display a detail card comparing collection metadata before and after an update.

    ``console`` is injected by the command's thin wrapper so unit tests that
    patch ``update.console`` still capture the print; it defaults to the shared
    console for direct/production use.

    Prints a formatted "Updated Collection" detail card containing any of the
    following rows when data is available: Collection name, Type, Documents
    (with delta), Chunks (with delta), Size (with delta), and Updated. Missing
    attributes are omitted.
    """

    def format_change(before_val, after_val) -> str | Text:
        """Format a value change with color coding.

        Returns a pre-built ``Text`` (never a bare markup string) — deltas are
        our own numbers, not user/document content, so the color tags here are
        legitimate and must render as styled markup rather than the literal
        text `create_info_rows_with_spacing` now gives plain strings
        (foundation/6c bug E2).
        """
        if before_val is None or after_val is None:
            return f"{before_val} → {after_val}"

        success = get_success_style()
        error = get_error_style()
        dim = get_dim_style()
        delta = after_val - before_val
        if delta > 0:
            return Text.from_markup(
                f"{before_val} → {after_val} ([{success}]+{delta}[/{success}])"
            )
        elif delta < 0:
            return Text.from_markup(
                f"{before_val} → {after_val} ([{error}]{delta}[/{error}])"
            )
        else:
            return Text.from_markup(
                f"{before_val} → {after_val} [{dim}](no change)[/{dim}]"
            )

    def format_size_change(before_bytes, after_bytes) -> str | Text:
        """Format size change with proper units (see format_change docstring)."""
        from indexed.cli.utils.format import format_size

        if before_bytes is None or after_bytes is None:
            return f"{before_bytes} → {after_bytes}"

        before_str = format_size(before_bytes)
        after_str = format_size(after_bytes)
        success = get_success_style()
        error = get_error_style()
        dim = get_dim_style()
        delta = after_bytes - before_bytes
        if delta > 0:
            return Text.from_markup(
                f"{before_str} → {after_str} ([{success}]+{format_size(delta)}[/{success}])"
            )
        elif delta < 0:
            return Text.from_markup(
                f"{before_str} → {after_str} ([{error}]{format_size(abs(delta))}[/{error}])"
            )
        else:
            return Text.from_markup(
                f"{before_str} → {after_str} [{dim}](no change)[/{dim}]"
            )

    # Build info rows for the card
    rows: list[tuple[str, str | Text]] = []

    # Collection name
    rows.append(("Collection", after.name))

    # Collection type
    if hasattr(after, "source_type") and after.source_type:
        rows.append(("Type", format_source_type(after.source_type)))

    # Documents count
    if hasattr(before, "number_of_documents") and hasattr(after, "number_of_documents"):
        before_docs = getattr(before, "number_of_documents", 0)
        after_docs = getattr(after, "number_of_documents", 0)
        rows.append(("Documents", format_change(before_docs, after_docs)))

    # Chunks count
    if hasattr(before, "number_of_chunks") and hasattr(after, "number_of_chunks"):
        before_chunks = getattr(before, "number_of_chunks", 0)
        after_chunks = getattr(after, "number_of_chunks", 0)
        rows.append(("Chunks", format_change(before_chunks, after_chunks)))

    # Size change
    if hasattr(before, "disk_size_bytes") and hasattr(after, "disk_size_bytes"):
        before_size = getattr(before, "disk_size_bytes", None)
        after_size = getattr(after, "disk_size_bytes", None)
        rows.append(("Size", format_size_change(before_size, after_size)))

    # Updated time (human-readable)
    if hasattr(after, "updated_time") and after.updated_time:
        from indexed.cli.utils.format import format_time

        readable_time = format_time(after.updated_time)
        rows.append(("Updated", readable_time))

    # Create card using the same component system as other commands
    card = create_detail_card(
        title="Updated Collection",
        rows=rows,
    )
    console.print(card)


@dataclass
class UpdateOutcome:
    """Aggregated result of a multi-collection update run."""

    successfully_updated: list[str] = field(default_factory=list)
    failed_collections: list[str] = field(default_factory=list)
    updated_collections: list[dict] = field(default_factory=list)
    total_docs: int = 0
    total_chunks: int = 0
    docs_delta: int = 0
    chunks_delta: int = 0


def resolve_collections_to_update(
    cmd: Any, *, collection: str | None, collections_path: str, simple: bool
) -> list[str] | None:
    """Resolve which collections to update.

    Returns the list of collection names, or ``None`` when there is nothing to
    do (the "no collections" message was already emitted — the command should
    return cleanly). Raises ``typer.Exit(1)`` when a *named* collection does not
    exist.
    """
    if collection is None:
        all_statuses = cmd.svc_status(collections_path=collections_path)
        if not all_statuses:
            if simple:
                print_json({"error": "No collections found"})
                return None
            cmd.console.print(
                f"\n[{get_dim_style()}]No collections found to update[/{get_dim_style()}]"
            )
            cmd.console.print(
                f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
            )
            return None

        collections = [s.name for s in all_statuses]
        if not simple and len(collections) > 1:
            # Collection names are user-controlled — escape the assembled
            # display string before it enters this markup f-string.
            names = escape(", ".join(f'"{n}"' for n in collections))
            cmd.console.print(
                f"\n[{get_heading_style()}]Updating {len(collections)} Collections: {names}[/{get_heading_style()}]"
            )
        return collections

    statuses = cmd.svc_status([collection], collections_path=collections_path)
    if not statuses:
        if simple:
            print_json(
                {"status": "error", "error": f"Collection '{collection}' not found"}
            )
        else:
            cmd.print_error(f"Collection '{collection}' not found")
        raise typer.Exit(1)

    return [collection]


def capture_before_state(
    cmd: Any, *, collections: list[str], collections_path: str, simple: bool
) -> dict[str, Any]:
    """Snapshot each collection's pre-update inspect result.

    Raises ``typer.Exit(1)`` if any collection cannot be inspected before the
    update — the update deltas can't be computed without a baseline.
    """
    before_data: dict[str, Any] = {}
    for coll_name in collections:
        inspect_result = cmd.inspect([coll_name], collections_path=collections_path)
        if not inspect_result:
            msg = f"Cannot inspect collection '{coll_name}' before update"
            if simple:
                print_json({"status": "error", "error": msg})
            else:
                cmd.print_error(msg)
            raise typer.Exit(1)
        before_data[coll_name] = inspect_result[0]
    return before_data


def run_update_loop(
    cmd: Any,
    *,
    collections: list[str],
    before_data: dict[str, Any],
    update_wiring: dict[str, Any],
    collections_path: str,
    config_service: Any,
    simple: bool,
    noop_context: Any,
    create_phased_progress: Any,
    ensure_credentials: Any,
) -> UpdateOutcome:
    """Update each collection with individual progress.

    A per-collection failure must not abort the remaining collections
    (foundation/6 E8): every collection is attempted and failures are collected
    so a single bad collection can't leave later ones stale/unlisted.

    The lazy services + rendering seams are reached through ``cmd`` (the update
    command module) so tests patch one place. ``noop_context`` /
    ``create_phased_progress`` / ``ensure_credentials`` are passed in from the
    command instead — the command still owns those imports (and the UI-parity
    source scan expects ``create_phased_progress`` to live in ``update.py``),
    and reading them from the command's namespace preserves test patching.
    """
    outcome = UpdateOutcome()

    for coll_name in collections:
        # Start each collection with a clean in-memory overlay (R3): the shared
        # manifest_factory applies this collection's stored settings via
        # from_manifest, and connectors that set some keys conditionally (Outline)
        # would otherwise inherit a previous collection's overlay value. Mirrors
        # the create path's clear_overlay bracketing (_create_helpers.py).
        config_service.clear_overlay()

        # Get collection status to build proper SourceConfig
        coll_statuses = cmd.svc_status([coll_name], collections_path=collections_path)
        if not coll_statuses:
            cmd.print_error(f"Collection '{coll_name}' not found during update")
            outcome.failed_collections.append(coll_name)
            continue
        coll_status = coll_statuses[0]

        # Ensure credentials are available for this source type
        source_type = getattr(coll_status, "source_type", None) or "localFiles"
        if source_type:
            ensure_credentials(source_type, config_service)

        if not coll_status.indexers:
            cmd.print_error(f"Collection '{coll_name}' has no indexers configured")
            outcome.failed_collections.append(coll_name)
            continue

        source_config = cmd.SourceConfig(
            name=coll_name,
            type=source_type,
            base_url_or_path="",
            indexer=coll_status.indexers[0],
        )

        if simple or cmd.is_verbose_mode():
            # Simple output / verbose mode: no progress display
            try:
                with noop_context():
                    cmd.update_service([source_config], **update_wiring)
                outcome.successfully_updated.append(coll_name)
            except Exception as e:
                if not simple:
                    cmd.print_error(f"Failed to update collection '{coll_name}': {e!s}")
                outcome.failed_collections.append(coll_name)
                continue
        else:
            reader_cfg = _read_manifest_reader_config(coll_name, collections_path)
            _display_collection_update_header(
                coll_name, source_type, reader_cfg, console=cmd.console
            )

            coll_error: Exception | None = None
            with create_phased_progress(title=None) as phased:
                try:
                    cmd.update_service(
                        [source_config], phased_progress=phased, **update_wiring
                    )
                except Exception as e:
                    coll_error = e

            cmd.console.print()
            if coll_error is None:
                after_result = cmd.inspect(
                    [coll_name], collections_path=collections_path
                )
                if after_result:
                    after_info = after_result[0]
                    before_info = before_data[coll_name]
                    cmd._format_update_comparison(before_info, after_info)
                    outcome.total_docs += after_info.number_of_documents
                    outcome.total_chunks += after_info.number_of_chunks
                    outcome.docs_delta += (
                        after_info.number_of_documents - before_info.number_of_documents
                    )
                    outcome.chunks_delta += (
                        after_info.number_of_chunks - before_info.number_of_chunks
                    )
                    outcome.updated_collections.append(
                        {
                            "name": coll_name,
                            "documents": after_info.number_of_documents,
                            "chunks": after_info.number_of_chunks,
                            "documents_delta": after_info.number_of_documents
                            - before_info.number_of_documents,
                            "chunks_delta": after_info.number_of_chunks
                            - before_info.number_of_chunks,
                        }
                    )
                cmd.console.print()
                print_success(f"Collection '{coll_name}' updated")
                cmd.console.print()
            else:
                cmd.print_error(f"Collection '{coll_name}' update failed: {coll_error}")
                outcome.failed_collections.append(coll_name)
                continue

    return outcome


def aggregate_simple_outcome(
    cmd: Any,
    outcome: UpdateOutcome,
    before_data: dict[str, Any],
    collections_path: str,
) -> None:
    """Fill in the JSON-mode totals for each successfully updated collection.

    The simple-output loop only records which collections succeeded; the
    per-collection document/chunk counts (and deltas vs the before-state) are
    computed here by re-inspecting, mirroring the pre-refactor command body.
    """
    for coll_name in outcome.successfully_updated:
        inspect_result = cmd.inspect([coll_name], collections_path=collections_path)
        if inspect_result:
            after_info = inspect_result[0]
            before_info = before_data[coll_name]
            outcome.total_docs += after_info.number_of_documents
            outcome.total_chunks += after_info.number_of_chunks
            outcome.updated_collections.append(
                {
                    "name": coll_name,
                    "documents": after_info.number_of_documents,
                    "chunks": after_info.number_of_chunks,
                    "documents_delta": after_info.number_of_documents
                    - before_info.number_of_documents,
                    "chunks_delta": after_info.number_of_chunks
                    - before_info.number_of_chunks,
                }
            )


def build_result_summary_text(num_collections: int, outcome: UpdateOutcome) -> str:
    """Compose the multi-collection result line (shown only for >1 collection)."""
    total_docs = outcome.total_docs
    total_chunks = outcome.total_chunks
    docs_delta = outcome.docs_delta
    chunks_delta = outcome.chunks_delta

    if docs_delta == 0 and chunks_delta == 0:
        return (
            f"Checked {num_collections} Collections - all up to date "
            f"({total_docs} documents, {total_chunks} chunks)"
        )

    changes = []
    if docs_delta > 0:
        changes.append(f"+{docs_delta} documents")
    elif docs_delta < 0:
        changes.append(f"{docs_delta} documents")
    if chunks_delta > 0:
        changes.append(f"+{chunks_delta} chunks")
    elif chunks_delta < 0:
        changes.append(f"{chunks_delta} chunks")
    change_str = ", ".join(changes) if changes else "metadata updated"
    return (
        f"Updated {num_collections} Collections: {change_str} "
        f"(now {total_docs} documents, {total_chunks} chunks)"
    )
