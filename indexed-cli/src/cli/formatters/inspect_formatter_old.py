from __future__ import annotations

from typing import List

from core.v1.engine.services import CollectionStatus
from cli.utils.rich_console import make_table, human_size


def render_inspect_table(statuses: List[CollectionStatus], *, include_size: bool) -> object:
    if include_size:
        table = make_table("Name", "Type", "Docs", "Chunks", "Updated", "Size")
    else:
        table = make_table("Name", "Type", "Docs", "Chunks", "Updated")

    for s in statuses:
        name = s.name
        stype = s.source_type or "-"
        docs = str(s.number_of_documents)
        chunks = str(s.number_of_chunks)
        updated = s.updated_time or "-"
        if include_size:
            size = human_size(s.disk_size_bytes)
            table.add_row(name, stype, docs, chunks, updated, size)
        else:
            table.add_row(name, stype, docs, chunks, updated)

    return table


