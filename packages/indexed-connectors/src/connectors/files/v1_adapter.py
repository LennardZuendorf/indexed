"""Adapter mapping ParsedDocument to the v1 dict format consumed by core.

This is the *only* file that knows about the v1 dict contract. When core v2
lands, this adapter is swapped or removed — the reader and indexed-parsing
remain untouched.
"""

from __future__ import annotations

import os
from pathlib import Path

from parsing.schema import ParsedDocument


class V1FormatAdapter:
    """Convert between ``ParsedDocument`` and the v1 dict formats."""

    @staticmethod
    def reader_output(parsed: ParsedDocument, base_path: str) -> dict:
        """Map a ``ParsedDocument`` to the v1 *reader* dict format.

        Returns a dict compatible with the legacy ``read_all_documents()``
        output::

            {
                "fileRelativePath": str,
                "fileFullPath": str,
                "modifiedTime": str,
                "content": [{"text": str, "metadata": dict}, ...],
            }
        """
        abs_path = os.path.abspath(parsed.file_path)
        rel_path = os.path.relpath(abs_path, base_path)

        modified_time = parsed.metadata.get("modified_time", "")
        if not modified_time:
            try:
                mtime = Path(abs_path).stat().st_mtime
                import datetime

                modified_time = datetime.datetime.fromtimestamp(mtime).isoformat()
            except OSError:
                modified_time = ""

        content = [
            {"text": ch.contextualized_text, "metadata": ch.metadata}
            for ch in parsed.chunks
        ]

        return {
            "fileRelativePath": rel_path,
            "fileFullPath": abs_path,
            "modifiedTime": str(modified_time),
            "content": content,
        }

    @staticmethod
    def converter_output(parsed: ParsedDocument, base_path: str) -> list[dict]:
        """Map a ``ParsedDocument`` to the v1 *converter* list-of-dicts format.

        Returns a single-element list compatible with
        ``FilesDocumentConverter.convert()``::

            [{
                "id": str,
                "url": str,
                "modifiedTime": str,
                "text": str,
                "chunks": [{"indexedData": str, "metadata": dict}, ...],
            }]
        """
        abs_path = os.path.abspath(parsed.file_path)
        rel_path = os.path.relpath(abs_path, base_path)

        modified_time = parsed.metadata.get("modified_time", "")
        if not modified_time:
            try:
                mtime = Path(abs_path).stat().st_mtime
                import datetime

                modified_time = datetime.datetime.fromtimestamp(mtime).isoformat()
            except OSError:
                modified_time = ""

        full_text = "\n\n".join(ch.contextualized_text for ch in parsed.chunks).strip()
        combined_text = f"{rel_path}\n\n{full_text}" if full_text else rel_path

        # First chunk is always the file path (v1 convention)
        chunks: list[dict] = [{"indexedData": rel_path}]
        for ch in parsed.chunks:
            entry: dict = {"indexedData": ch.contextualized_text}
            if ch.metadata:
                entry["metadata"] = ch.metadata
            chunks.append(entry)

        return [
            {
                "id": rel_path,
                "url": f"file://{abs_path}",
                "modifiedTime": str(modified_time),
                "text": combined_text,
                "chunks": chunks,
            }
        ]
