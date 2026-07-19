"""Inspect command - Show indexed collections or detailed info about a specific collection.

This command both fetches collection data (using the core inspect() service) AND
contains all formatter logic (previously in inspect_formatter.py) for displaying
with Rich or JSON. Presentation and command logic are now unified in this file.
"""

import typer
from typing import Dict, List, Optional, TYPE_CHECKING
from rich.columns import Columns
from rich.markup import escape

from ...utils.console import console
from ...utils.simple_output import is_simple_output, print_json
from ...utils.components import (
    create_info_card,
    create_detail_card,
    get_heading_style,
    get_dim_style,
    create_summary,
    print_error,
)

if TYPE_CHECKING:
    from indexed.core.engine import CollectionInfo, EngineDescriptor

# ---- Use format_size and format_time from @format.py ----
from ...utils.format import format_size, format_time


def _format_engine_indicator(desc: "Optional[EngineDescriptor]") -> Optional[str]:
    """Human engine indicator (R13): ``v1`` or ``v2 · <provider> · <model> · <store>``.

    Additive — it never rewrites an existing row, so a v1-only listing gains at
    most one new "Engine" line and existing lines stay byte-stable (R6).
    """
    if desc is None:
        return None
    if desc.engine_version == "2":
        parts = ["v2"]
        if desc.embedding_provider:
            parts.append(desc.embedding_provider)
        if desc.embedding_model:
            parts.append(desc.embedding_model)
        if desc.vector_store:
            parts.append(desc.vector_store)
        return " · ".join(parts)
    return f"v{desc.engine_version}"


def _build_collection_rows(
    coll: "CollectionInfo",
    include_index: bool = False,
    include_created: bool = False,
    engine: "Optional[EngineDescriptor]" = None,
) -> list[tuple[str, str]]:
    """Build standard info rows for a collection.

    Centralizes row construction so all views (brief, verbose, detail)
    use the same labels and formatting. An engine indicator (R13) is prepended
    when a descriptor is supplied.
    """
    rows = []
    indicator = _format_engine_indicator(engine)
    if indicator:
        rows.append(("Engine", indicator))
    rows.append(("Type", coll.source_type or "Unknown"))
    if coll.relative_path:
        rows.append(("Path", coll.relative_path))
    rows.append(("Documents", str(coll.number_of_documents)))
    rows.append(("Chunks", str(coll.number_of_chunks)))
    if coll.disk_size_bytes:
        rows.append(("Size", format_size(coll.disk_size_bytes)))
    if include_index and coll.index_size_bytes:
        rows.append(("Index", format_size(coll.index_size_bytes)))
    if include_created and coll.created_time:
        rows.append(("Created", format_time(coll.created_time)))
    if coll.updated_time:
        rows.append(("Updated", format_time(coll.updated_time)))
    return rows


def format_collection_list(
    collections: List["CollectionInfo"],
    verbose: bool = False,
    engines: "Optional[Dict[str, EngineDescriptor]]" = None,
) -> None:
    """Display a list of collections with optional verbose detail."""
    engines = engines or {}
    if verbose:
        _show_verbose_list(collections, engines)
    else:
        _show_brief_list(collections, engines)


def _show_brief_list(
    collections: List["CollectionInfo"],
    engines: "Dict[str, EngineDescriptor]",
) -> None:
    """Show minimal collection info in compact cards."""
    console.print()
    count = len(collections)
    plural = "Collection" if count == 1 else "Collections"
    console.print(
        f"[{get_heading_style()}]{count} {plural} Details:[/{get_heading_style()}]"
    )
    console.print()

    panels = []
    total_docs = 0
    total_chunks = 0

    for coll in collections:
        total_docs += coll.number_of_documents
        total_chunks += coll.number_of_chunks

        rows = _build_collection_rows(coll, engine=engines.get(coll.name))
        card = create_info_card(title=coll.name, rows=rows)
        panels.append(card)

    if panels:
        console.print(Columns(panels, equal=True, expand=True))

    # Summary
    console.print()
    console.print(
        create_summary("Total", f"{total_docs} documents, {total_chunks} chunks")
    )
    console.print()


def _show_verbose_list(
    collections: List["CollectionInfo"],
    engines: "Dict[str, EngineDescriptor]",
) -> None:
    """Show detailed collection info for all collections with unified design."""
    console.print()
    count = len(collections)
    plural = "Collection" if count == 1 else "Collections"
    console.print(
        f"[{get_heading_style()}]{count} {plural} Details:[/{get_heading_style()}]"
    )
    console.print()

    total_docs = 0
    total_chunks = 0
    total_size = 0

    for coll in collections:
        total_docs += coll.number_of_documents
        total_chunks += coll.number_of_chunks
        if coll.disk_size_bytes:
            total_size += coll.disk_size_bytes

        rows = _build_collection_rows(
            coll,
            include_index=True,
            include_created=True,
            engine=engines.get(coll.name),
        )
        card = create_detail_card(title=coll.name, rows=rows)
        console.print(card)

    console.print()
    console.print(
        create_summary(
            "Total",
            f"{total_docs} documents, {total_chunks} chunks, {format_size(total_size)}",
        )
    )
    console.print()


def format_collection_detail(
    info: "CollectionInfo", engine: "Optional[EngineDescriptor]" = None
) -> None:
    """Display detailed information about a specific collection."""
    console.print()
    console.print(
        f"[{get_heading_style()}]{escape(info.name)} Collection Details:[/{get_heading_style()}]"
    )
    console.print()

    rows = _build_collection_rows(
        info, include_index=True, include_created=True, engine=engine
    )
    card = create_detail_card(title=info.name, rows=rows)
    console.print(card)
    console.print()


def _engine_json_fields(
    engine: "Optional[EngineDescriptor]",
) -> Dict[str, Optional[str]]:
    """R13 engine fields for the machine-readable inspect JSON (each row)."""
    return {
        "engine": engine.engine_version if engine else None,
        "embedding_model": engine.embedding_model if engine else None,
        "embedding_provider": engine.embedding_provider if engine else None,
        "vector_store": engine.vector_store if engine else None,
    }


def format_collection_json(
    info: "CollectionInfo", engine: "Optional[EngineDescriptor]" = None
) -> None:
    """Display collection info as JSON."""
    output = {
        "name": info.name,
        **_engine_json_fields(engine),
        "source_type": info.source_type,
        "path": info.relative_path,
        "number_of_documents": info.number_of_documents,
        "number_of_chunks": info.number_of_chunks,
        "disk_size_bytes": info.disk_size_bytes,
        "index_size_bytes": info.index_size_bytes,
        "created_time": info.created_time,
        "updated_time": info.updated_time,
    }
    print_json(output)


def format_collections_json(
    collections: List["CollectionInfo"],
    engines: "Optional[Dict[str, EngineDescriptor]]" = None,
) -> None:
    """Display a list of collections in JSON."""
    engines = engines or {}
    output = [
        {
            "name": c.name,
            **_engine_json_fields(engines.get(c.name)),
            "source_type": c.source_type,
            "path": c.relative_path,
            "number_of_documents": c.number_of_documents,
            "number_of_chunks": c.number_of_chunks,
            "disk_size_bytes": c.disk_size_bytes,
            "index_size_bytes": c.index_size_bytes,
            "created_time": c.created_time,
            "updated_time": c.updated_time,
        }
        for c in collections
    ]
    print_json(output)


# ---- END FORMATTER LOGIC ----


def inspect_collections(
    ctx: typer.Context,
    name: str = typer.Argument(None, help="Collection name to inspect in detail"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information for all collections"
    ),
) -> None:
    """Show all indexed collections or inspect a specific collection.

    Examples:
        indexed inspect                            # List all collections
        indexed inspect my-collection              # Detailed info about specific collection
        indexed inspect --verbose                  # Detailed info about all collections
        indexed --simple-output inspect            # JSON output
    """
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import inspect as this_module
    from indexed.cli.composition import resolve_collections_context

    inspect_svc = this_module.inspect
    collection_exists_svc = this_module.collection_exists
    engine_descriptors_svc = this_module.engine_descriptors

    mode_override = ctx.obj.get("mode_override") if ctx.obj else None
    cli_ctx = resolve_collections_context(mode_override=mode_override)
    collections_path = str(cli_ctx.collections_path)

    # Pass an explicit --engine through so the facade raises on a wrong engine
    # (R2); omit when unset so v1 behavior is unchanged.
    engine_flag = ctx.obj.get("engine") if ctx.obj else None
    engine_kwargs = {"engine": engine_flag} if engine_flag is not None else {}

    def _descriptors_for(
        colls: List["CollectionInfo"],
    ) -> Dict[str, "EngineDescriptor"]:
        """Engine identity (R13) for the collections about to be displayed.

        Reads only manifests (no index/model). Never fails the command — the
        facade helper omits anything it can't classify.
        """
        names = [c.name for c in colls]
        return {
            d.name: d
            for d in engine_descriptors_svc(names, collections_path=collections_path)
        }

    # Fetch collection info from core - this is connection-agnostic
    if name:
        # Inspect specific collection (no progress bar)
        collections = inspect_svc(
            [name], collections_path=collections_path, **engine_kwargs
        )

        # Check if collection exists and has valid data
        if not collections or collections[0].number_of_documents == 0:
            # Check if it truly doesn't exist vs just being empty
            all_collections = inspect_svc(collections_path=collections_path)
            exists = any(c.name == name for c in all_collections)

            if not exists:
                # inspect() OMITS collections whose manifest can't be read
                # (foundation/6 E1) — but a directory that still exists on
                # disk, corrupt or not, deserves an honest status rather than
                # a misleading "not found" (foundation/6 regression fix).
                if collection_exists_svc(
                    name, collections_path=collections_path, **engine_kwargs
                ):
                    print_error(f"Collection '{name}' is corrupt or unreadable")
                    console.print()
                    raise typer.Exit(1)

                print_error(f"Collection '{name}' not found")
                if all_collections:
                    console.print(
                        f"\n[{get_dim_style()}]Available collections:[/{get_dim_style()}]"
                    )
                    for coll in all_collections:
                        console.print(f"  • {escape(coll.name)}")
                console.print()
                raise typer.Exit(1)

        # Format and display single collection
        descriptors = _descriptors_for(collections[:1])
        engine = descriptors.get(collections[0].name)
        if is_simple_output():
            format_collection_json(collections[0], engine)
        else:
            format_collection_detail(collections[0], engine)
    else:
        # List all collections (no progress bar)
        collections = inspect_svc(collections_path=collections_path)

        if not collections:
            console.print(
                f"\n[{get_dim_style()}]No collections found[/{get_dim_style()}]"
            )
            console.print(
                f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
            )
            return

        # Format and display list
        descriptors = _descriptors_for(collections)
        if is_simple_output():
            format_collections_json(collections, descriptors)
        else:
            format_collection_list(collections, verbose=verbose, engines=descriptors)


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "inspect":
        from indexed.core.engine import inspect

        return inspect
    elif name == "collection_exists":
        from indexed.core.engine import collection_exists

        return collection_exists
    elif name == "engine_descriptors":
        from indexed.core.engine import engine_descriptors

        return engine_descriptors
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# For Typer command registration
app = typer.Typer(help="Inspect indexed collections")
app.command(name="inspect")(inspect_collections)
