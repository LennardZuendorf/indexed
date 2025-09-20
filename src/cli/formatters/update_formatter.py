from __future__ import annotations

import logging
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from typing import Iterator, List, Dict, Any
from io import StringIO

from cli.utils.rich_console import console, transient_spinner
from cli.formatters.inspect_formatter import render_inspect_table


class UpdateProgress:
    """Helper class to track update progress and results."""
    
    def __init__(self):
        self.results: Dict[str, Dict[str, Any]] = {}
        self.total_docs = 0
        self.total_collections = 0
    
    def add_result(self, collection_name: str, docs: int, chunks: int):
        """Add result for a collection."""
        self.results[collection_name] = {"docs": docs, "chunks": chunks}
        self.total_docs += docs
        self.total_collections += 1


def show_update_start(collection_names: List[str]) -> None:
    """Show initial update message."""
    if len(collection_names) == 1:
        console.print(f"\n🗄️ Running update of collection '{collection_names[0]}'\n")
    else:
        console.print(f"\n🗄️ Running update of {len(collection_names)} collections")


@contextmanager
def update_collection(collection_name: str) -> Iterator[None]:
    """Context manager for updating a single collection."""
    # Suppress verbose output by redirecting stdout/stderr and raising log level temporarily
    original_level = logging.getLogger().level
    
    if collection_name == "multiple collections":
        spinner_text = "Updating collections...\n"
        success_text = "✅ Updated collections \n"
    else:
        spinner_text = f"Updating '{collection_name}'... \n"
        success_text = f"✅ Updated '{collection_name}' \n"
    
    with transient_spinner(spinner_text) as spinner:
        try:
            # Temporarily raise logging level to suppress INFO logs
            logging.getLogger().setLevel(logging.WARNING)
            
            # Suppress tqdm and other stdout/stderr output
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                yield
            
            # Success - show result for this collection
            spinner.stop()
            console.print(success_text)
            
        except Exception:
            # Error - let it propagate, spinner will stop automatically
            spinner.stop()
            raise
        finally:
            # Restore original logging level
            logging.getLogger().setLevel(original_level)


def show_update_summary(collection_count: int, total_docs: int = 0, collection_statuses=None) -> None:
    """Show final update summary and current colle ction status."""
    if collection_count == 1:
        if total_docs > 0:
            console.print(f"Completed update of 1 collection, indexed {total_docs} documents.\n")
        else:
            console.print("Completed update of 1 collection.\n")
    else:
        if total_docs > 0:
            console.print(f"Completed update of {collection_count} collections, indexed {total_docs} documents.\n")
        else:
            console.print(f"Completed update of {collection_count} collections.\n")
    
    # Show current collection status like inspect command
    if collection_statuses:
        console.print("\n📊 Current collection status:")
        table = render_inspect_table(collection_statuses, include_size=False)
        console.print(table)
        console.print()
