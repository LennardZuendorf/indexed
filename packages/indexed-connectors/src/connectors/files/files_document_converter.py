"""File-system document converter.

With the parsing upgrade the reader already yields pre-chunked content via
indexed-parsing.  The converter's job is simplified: it takes the v1 reader
dict and maps each content part as-is (no more RecursiveCharacterTextSplitter).
"""

from __future__ import annotations


class FilesDocumentConverter:
    """Convert v1 reader dicts to v1 indexed-document dicts."""

    def convert(self, document: dict) -> list[dict]:
        return [
            {
                "id": document["fileRelativePath"],
                "url": self._build_url(document),
                "modifiedTime": document["modifiedTime"],
                "text": self._build_document_text(document),
                "chunks": self._split_to_chunks(document),
            }
        ]

    def _build_document_text(self, document: dict) -> str:
        content = self._convert_to_text(
            [content_part["text"] for content_part in document["content"]], ""
        )
        return self._convert_to_text([document["fileRelativePath"], content])

    @staticmethod
    def _convert_to_text(elements: list[str], delimiter: str = "\n\n") -> str:
        return delimiter.join([e for e in elements if e]).strip()

    @staticmethod
    def _split_to_chunks(document: dict) -> list[dict]:
        chunks: list[dict] = [{"indexedData": document["fileRelativePath"]}]

        for content_part in document["content"]:
            text = content_part["text"].strip()
            if text:
                entry: dict = {"indexedData": text}
                if "metadata" in content_part and content_part["metadata"]:
                    entry["metadata"] = content_part["metadata"]
                chunks.append(entry)

        return chunks

    @staticmethod
    def _build_url(document: dict) -> str:
        return f"file://{document['fileFullPath']}"
