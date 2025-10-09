from __future__ import annotations

from typing import Iterable, List

from cli.utils.rich_console import console
from cli.formatters.inspect_formatter import render_inspect_table
from core.v1.engine.services import CollectionStatus


def render_delete_candidates(statuses: Iterable[CollectionStatus]) -> None:
    items: List[CollectionStatus] = list(statuses)
    if not items:
        console.print("\n📂 No collections found.\n")
        return

    count = len(items)
    if count == 1:
        console.print("\n📂 Candidate collection to delete:\n")
    else:
        console.print(f"\n📂 {count} candidate collections to delete:\n")

    table = render_inspect_table(items, include_size=False)
    console.print(table)


def show_delete_result(deleted_names: List[str]) -> None:
    if not deleted_names:
        console.print("\nNo collections deleted.\n")
        return
    if len(deleted_names) == 1:
        console.print(f"\nDeleted collection '{deleted_names[0]}'.\n")
    else:
        console.print(f"\nDeleted {len(deleted_names)} collections.\n")


