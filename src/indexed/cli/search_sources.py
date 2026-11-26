"""The sources a search intends to use — the input to the payload's ``sources``.

The core engine can only answer for collections it could read, so its dict is
the *answered* scope. A search also has an *intended* scope: the workspace
selection's names, or the one collection ``--collection`` named. Everything the
engine never saw (a collection whose data was deleted, one with no usable
index) used to vanish from the payload entirely — this module turns the intent
into the declarations ``build_search_payload`` needs, so the payload can name
the gap (#340 R2).

It lives in ``cli`` because it reads collection status through the core facade
and both the CLI command and the MCP tools declare their scope here; it is not
presentation and it never prints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

#: Declaration statuses that mean "this source did not answer". The builder
#: treats every one of them as an error the payload must also carry.
NON_ANSWERING = frozenset({"empty", "missing", "unusable", "failed"})


def declare_sources(
    *,
    names: Sequence[str],
    statuses: Sequence[Any] = (),
    unresolved: Sequence[Any] = (),
) -> List[Dict[str, Any]]:
    """One declaration per intended source name, in the order given.

    ``names`` is the intended scope; ``statuses`` are the ``CollectionStatus``
    objects the caller already fetched (only resolvable collections appear);
    ``unresolved`` are ``workspace_selection.UnresolvedEntry`` records for
    entries the store no longer serves. A name with neither a status nor an
    unresolved record is on disk but unusable, and says so.
    """
    by_name = {getattr(status, "name", ""): status for status in statuses}
    unresolved_by_name = {getattr(entry, "name", ""): entry for entry in unresolved}
    declarations: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        status = by_name.get(name)
        if status is not None and getattr(status, "indexers", None):
            declaration: Dict[str, Any] = {"collection": name}
            source_type = getattr(status, "source_type", None)
            if source_type:
                declaration["source_type"] = str(source_type)
            documents = getattr(status, "number_of_documents", None)
            if isinstance(documents, int):
                declaration["documents"] = documents
            declarations.append(declaration)
            continue
        missing: Optional[Any] = unresolved_by_name.get(name)
        if missing is not None:
            declarations.append(
                {
                    "collection": name,
                    "status": "missing",
                    "error": str(getattr(missing, "reason", "")),
                }
            )
            continue
        declarations.append(
            {
                "collection": name,
                "status": "unusable",
                "error": (
                    f"Collection '{name}' is in the store but has no usable "
                    "index; re-run indexing for it, then retry."
                ),
            }
        )
    return declarations


def scope_of(
    selection: Optional[Any],
    statuses: Sequence[Any],
) -> tuple[List[str], List[Any]]:
    """The intended names and unresolved entries for a search.

    With a selection, the definition decides the scope (in definition order,
    including entries that no longer resolve). Without one, the store does —
    that is the pre-#344 behaviour, and every name has a status.
    """
    if selection is None:
        return [getattr(status, "name", "") for status in statuses], []
    return list(selection.scope), list(getattr(selection, "unresolved", ()))


def declarations_by_name(
    declarations: Sequence[Mapping[str, Any]],
) -> Dict[str, Mapping[str, Any]]:
    """Index declarations by collection, for callers that need the verdict."""
    return {str(entry["collection"]): entry for entry in declarations}
