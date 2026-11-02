"""Stable generated path context at the evaluator's conversion boundary."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

POLICY = "eval-corpus-relative-v1"


class CanonicalConverter:
    """Delegate to the genuine converter after replacing known leading context."""

    def __init__(self, converter: Any) -> None:
        self.converter = converter
        self.records: list[dict[str, Any]] = []

    def convert(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        normalized = deepcopy(document)
        physical, relative = document["fileFullPath"], document["fileRelativePath"]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("evaluation document must have a corpus-relative path")
        for part in normalized["content"]:
            if part.get("metadata", {}).get("file_path") != physical:
                continue
            for marker in ("# ", ""):
                prefix = f"{marker}{physical}\n"
                if part["text"].startswith(prefix):
                    part["text"] = (
                        f"{marker}eval/corpus/{path.as_posix()}\n"
                        + part["text"][len(prefix) :]
                    )
                    break
        converted = self.converter.convert(normalized)
        for doc in converted:
            texts = [chunk["indexedData"] for chunk in doc["chunks"]]
            self.records.append(
                {
                    "id": doc["id"],
                    "chunks": len(texts),
                    "sha256": sha256(
                        json.dumps(
                            texts, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                }
            )
        return converted

    def evidence(self) -> dict[str, Any]:
        records = sorted(self.records, key=lambda record: record["id"])
        return {
            "boundary": "normalized-converter-chunks",
            "documents": records,
            "sha256": sha256(
                json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }


class CanonicalConnector:
    """Preserve the side connector's reader and all non-converter behavior."""

    def __init__(self, connector: Any, converter: CanonicalConverter) -> None:
        self.connector, self.converter = connector, converter

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connector, name)


class CanonicalFactory:
    """Callable injection seam also owns the measurement's input receipt."""

    policy = POLICY

    def __init__(self, corpus_dir: Path) -> None:
        self.corpus_dir = corpus_dir
        self.converters: list[CanonicalConverter] = []

    def __call__(self, _config: Any) -> CanonicalConnector:
        from indexed.connectors.files.connector import FileSystemConnector

        connector = FileSystemConnector(path=str(self.corpus_dir))
        converter = CanonicalConverter(connector.converter)
        self.converters.append(converter)
        return CanonicalConnector(connector, converter)

    def evidence(self) -> dict[str, Any]:
        combined = CanonicalConverter(None)
        combined.records = [
            record for converter in self.converters for record in converter.records
        ]
        return combined.evidence()
