from datetime import datetime, timezone
from enum import Enum

import numpy as np
from loguru import logger

try:
    import orjson

    def _json_loads(data):
        return orjson.loads(data)

    def _json_dumps(data, indent=False):
        opts = orjson.OPT_INDENT_2 if indent else 0
        return orjson.dumps(data, option=opts | orjson.OPT_NON_STR_KEYS).decode("utf-8")
except ImportError:
    import json

    def _json_loads(data):
        return json.loads(data)

    def _json_dumps(data, indent=False):
        return json.dumps(data, indent=2 if indent else None, ensure_ascii=False)


# Core accepts optional progress callbacks for CLI/UI visibility into long-running operations.
from utils.performance import log_execution_duration
from core.v1.engine.services.models import (
    ProgressUpdate,
    ProgressCallback,
    PhasedProgressCallback,
)


class OPERATION_TYPE(Enum):
    CREATE = "create"
    UPDATE = "update"


class DocumentCollectionCreator:
    def __init__(
        self,
        collection_name: str,
        document_reader,
        document_converter,
        document_indexers,
        persister,
        operation_type: OPERATION_TYPE = OPERATION_TYPE.CREATE,
        indexing_batch_size=500_000,
        progress_callback: ProgressCallback = None,
        phased_progress: PhasedProgressCallback = None,
        explicit_deletions: list[str] | None = None,
    ):
        self.operation_type = operation_type
        self.collection_name = collection_name
        self.document_reader = document_reader
        self.document_converter = document_converter
        self.document_indexers = document_indexers
        self.persister = persister
        self.indexing_batch_size = indexing_batch_size
        self.progress_callback = progress_callback
        self.phased_progress = phased_progress
        self.explicit_deletions = explicit_deletions or []

    def run(self):
        if self.operation_type == OPERATION_TYPE.CREATE:
            self.__create_collection()
            return

        if self.operation_type == OPERATION_TYPE.UPDATE:
            self.__update_collection()
            return

        raise ValueError(f"Unknown operation type: {self.operation_type}")

    def __create_collection(self):
        self.persister.remove_folder(self.collection_name)
        self.persister.create_folder(self.collection_name)

        update_time = datetime.now(timezone.utc)

        document_ids, number_of_expected_documents = log_execution_duration(
            lambda: self.__read_documents(),
            identifier=f"Reading documents for collection: {self.collection_name}",
        )

        if len(document_ids) == 0:
            self.persister.remove_folder(self.collection_name)
            reader = self.document_reader
            if hasattr(reader, "reader"):
                reader = reader.reader
            details = []
            base_path = getattr(reader, "base_path", None)
            include_patterns = getattr(reader, "include_patterns", None)
            exclude_patterns = getattr(reader, "exclude_patterns", None)
            if base_path:
                details.append(f"source path: {base_path}")
            if include_patterns is not None:
                details.append(f"include patterns: {include_patterns}")
            if exclude_patterns is not None:
                details.append(f"exclude patterns: {exclude_patterns}")
            detail_str = f" ({', '.join(details)})" if details else ""
            raise ValueError(
                f"No documents found for collection '{self.collection_name}'{detail_str}. "
                "Check that the source path exists and contains readable files."
            )

        last_modified_document_time, number_of_chunks = log_execution_duration(
            lambda: self.__index_documents_for_new_collection(document_ids),
            identifier=f"Indexing documents for collection: {self.collection_name}",
        )

        if self.phased_progress:
            self.phased_progress.finish_phase("Generating Embeddings")

        manifest = self.__create_manifest_file(
            update_time, last_modified_document_time, number_of_chunks
        )

        if number_of_expected_documents != len(document_ids):
            logger.warning(
                f"Expected number of documents: {number_of_expected_documents} does not match actual number of read documents: {len(document_ids)}. Usually it happens when an error occurs during document reading. Please check logs for more details."
            )

        logger.info(
            f"Collection successfully created: \n{_json_dumps(manifest, indent=True)}"
        )

    def __update_collection(self):
        if not self.persister.is_path_exists(self.collection_name):
            raise Exception(
                f"Collection {self.collection_name} does not exist. Please create it first."
            )

        manifest = _json_loads(
            self.persister.read_text_file(self.__build_manifest_path())
        )

        update_time = datetime.now(timezone.utc)

        if self.explicit_deletions:
            log_execution_duration(
                lambda: self.__remove_explicit_deletions(self.explicit_deletions),
                identifier=f"Removing deleted documents from collection: {self.collection_name}",
            )

        document_ids, number_of_expected_documents = log_execution_duration(
            lambda: self.__read_documents(),
            identifier=f"Reading documents for collection: {self.collection_name}",
        )

        if len(document_ids) == 0 and not self.explicit_deletions:
            logger.info(
                "No new documents found for collection update. Updating timestamp only."
            )
            # Update only the timestamp in manifest to record that we checked for updates
            manifest["updatedTime"] = update_time.isoformat()
            self.__save_json_file(manifest, self.__build_manifest_path())
            return

        if len(document_ids) == 0:
            # Only deletions — update manifest counts without re-indexing
            manifest["updatedTime"] = update_time.isoformat()
            manifest["numberOfDocuments"] = len(
                self.persister.read_folder_files(f"{self.collection_name}/documents")
            )
            manifest["numberOfChunks"] = self.document_indexers[0].get_size()
            self.__save_json_file(manifest, self.__build_manifest_path())
            logger.info(
                f"Collection successfully updated (deletions only): \n{_json_dumps(manifest, indent=True)}"
            )
            return

        last_modified_document_time, number_of_chunks = log_execution_duration(
            lambda: self.__index_documents_for_existing_collection(document_ids),
            identifier=f"Indexing documents for collection: {self.collection_name}",
        )

        if self.phased_progress:
            self.phased_progress.finish_phase("Generating Embeddings")

        manifest = self.__create_manifest_file(
            update_time,
            last_modified_document_time,
            number_of_chunks,
            existing_manifest=manifest,
        )

        if number_of_expected_documents != len(document_ids):
            logger.warning(
                f"Expected number of documents: {number_of_expected_documents} does not match actual number of read documents: {len(document_ids)}. Usually it happens when an error occurs during document reading. Please check logs for more details."
            )

        logger.info(
            f"Collection successfully updated: \n{_json_dumps(manifest, indent=True)}"
        )

    def __read_documents(self):
        document_ids = []

        number_of_expected_documents = self.document_reader.get_number_of_documents()

        if self.progress_callback:
            self.progress_callback(
                ProgressUpdate(
                    stage="reading",
                    current=0,
                    total=number_of_expected_documents,
                    message="Reading documents...",
                )
            )

        if self.phased_progress:
            self.phased_progress.start_phase(
                "Fetching Documents",
                total=number_of_expected_documents
                if number_of_expected_documents
                else None,
            )

        for idx, document in enumerate(self.document_reader.read_all_documents(), 1):
            for converted_document in self.document_converter.convert(document):
                document_path = (
                    f"{self.collection_name}/documents/{converted_document['id']}.json"
                )
                self.__save_json_file(converted_document, document_path)

                document_ids.append(converted_document["id"])

            if self.progress_callback:
                self.progress_callback(
                    ProgressUpdate(
                        stage="reading",
                        current=idx,
                        total=number_of_expected_documents,
                        message=f"Reading documents: {idx}/{number_of_expected_documents}",
                    )
                )

            if self.phased_progress:
                self.phased_progress.advance("Fetching Documents")

        if self.phased_progress:
            self.phased_progress.finish_phase("Fetching Documents")

        return document_ids, number_of_expected_documents

    def __index_documents_for_new_collection(self, document_ids):
        index_mapping = {}
        reverse_index_mapping = {}
        last_index_item_id = -1

        return self.__add_documents_to_index(
            document_ids, index_mapping, reverse_index_mapping, last_index_item_id
        )

    def __index_documents_for_existing_collection(self, document_ids):
        index_mapping = _json_loads(
            self.persister.read_text_file(self.__build_index_mapping_path())
        )
        reverse_index_mapping = _json_loads(
            self.persister.read_text_file(self.__build_reverse_index_mapping_path())
        )
        index_info = _json_loads(
            self.persister.read_text_file(self.__build_index_info_path())
        )
        last_index_item_id = index_info["lastIndexItemId"]

        self.__remove_documents_from_index(
            document_ids, index_mapping, reverse_index_mapping
        )

        return self.__add_documents_to_index(
            document_ids, index_mapping, reverse_index_mapping, last_index_item_id
        )

    def __add_documents_to_index(
        self, document_ids, index_mapping, reverse_index_mapping, last_index_item_id
    ):
        last_modified_document_time = None
        total_docs = len(document_ids)
        processed = 0

        if self.progress_callback:
            self.progress_callback(
                ProgressUpdate(
                    stage="indexing",
                    current=0,
                    total=total_docs,
                    message="Indexing documents...",
                )
            )

        for batch_document_ids in self.__batch_items(
            document_ids, self.indexing_batch_size
        ):
            items_to_index = []
            index_item_ids = []

            for document_id in batch_document_ids:
                document_path = f"{self.collection_name}/documents/{document_id}.json"

                converted_document = _json_loads(
                    self.persister.read_text_file(document_path)
                )

                modified_document_time = datetime.fromisoformat(
                    converted_document["modifiedTime"]
                )
                if (
                    last_modified_document_time is None
                    or last_modified_document_time < modified_document_time
                ):
                    last_modified_document_time = modified_document_time

                for chunk_number in range(0, len(converted_document["chunks"])):
                    last_index_item_id += 1

                    items_to_index.append(
                        converted_document["chunks"][chunk_number]["indexedData"]
                    )
                    index_item_ids.append(last_index_item_id)

                    index_mapping[last_index_item_id] = {
                        "documentId": converted_document["id"],
                        "documentUrl": converted_document["url"],
                        "documentPath": document_path,
                        "chunkNumber": chunk_number,
                    }

                    if converted_document["id"] not in reverse_index_mapping:
                        reverse_index_mapping[converted_document["id"]] = []
                    reverse_index_mapping[converted_document["id"]].append(
                        last_index_item_id
                    )

            # Start embedding phase with chunk-level tracking
            if self.phased_progress:
                self.phased_progress.start_phase(
                    "Generating Embeddings", total=len(items_to_index)
                )

            embedding_progress = None
            if self.phased_progress:

                def embedding_progress(n: int) -> None:
                    self.phased_progress.advance("Generating Embeddings", amount=n)

            for indexer in self.document_indexers:
                indexer.index_texts(
                    index_item_ids, items_to_index, progress_callback=embedding_progress
                )

            processed += len(batch_document_ids)
            if self.progress_callback:
                self.progress_callback(
                    ProgressUpdate(
                        stage="indexing",
                        current=processed,
                        total=total_docs,
                        message=f"Indexing: {processed}/{total_docs} documents",
                    )
                )

        for indexer in self.document_indexers:
            # Save in native FAISS format for memory-mapped loading
            self.persister.save_faiss_index(
                indexer.get_faiss_index(),
                f"{self.__build_index_base_path(indexer)}/indexer.faiss",
            )
            # Also save legacy pickle format for backward compatibility
            self.persister.save_bin_file(
                indexer.serialize(), f"{self.__build_index_base_path(indexer)}/indexer"
            )

        index_info = {
            "lastIndexItemId": last_index_item_id,
        }
        self.__save_json_file(index_info, self.__build_index_info_path())
        self.__save_json_file(index_mapping, self.__build_index_mapping_path())
        self.__save_json_file(
            reverse_index_mapping, self.__build_reverse_index_mapping_path()
        )

        return last_modified_document_time, self.document_indexers[0].get_size()

    def __remove_documents_from_index(
        self, document_ids, index_mapping, reverse_index_mapping
    ):
        for batch_document_ids in self.__batch_items(
            document_ids, self.indexing_batch_size
        ):
            index_ids_to_remove = []

            for document_id in batch_document_ids:
                if document_id in reverse_index_mapping:
                    document_index_ids_to_remove = reverse_index_mapping[document_id]

                    index_ids_to_remove.extend(document_index_ids_to_remove)

                    for index_id in document_index_ids_to_remove:
                        index_mapping.pop(str(index_id), None)
                    del reverse_index_mapping[document_id]

            for indexer in self.document_indexers:
                indexer.remove_ids(np.array(index_ids_to_remove))

    def __remove_explicit_deletions(self, doc_ids: list[str]) -> None:
        """Remove explicitly deleted documents (by document ID) from the index.

        Called during updates when the ChangeTracker reports deleted files.
        Document IDs for local files are relative file paths (e.g. ``utils/retry.py``).
        """
        if not doc_ids:
            return

        for doc_id in doc_ids:
            doc_file = f"{self.collection_name}/documents/{doc_id}.json"
            if self.persister.is_path_exists(doc_file):
                self.persister.remove_file(doc_file)

        index_mapping = _json_loads(
            self.persister.read_text_file(self.__build_index_mapping_path())
        )
        reverse_index_mapping = _json_loads(
            self.persister.read_text_file(self.__build_reverse_index_mapping_path())
        )

        self.__remove_documents_from_index(
            doc_ids, index_mapping, reverse_index_mapping
        )

        self.__save_json_file(index_mapping, self.__build_index_mapping_path())
        self.__save_json_file(
            reverse_index_mapping, self.__build_reverse_index_mapping_path()
        )

    def __build_reverse_index_mapping_path(self):
        return f"{self.collection_name}/indexes/reverse_index_document_mapping.json"

    def __build_index_mapping_path(self):
        return f"{self.collection_name}/indexes/index_document_mapping.json"

    def __build_index_info_path(self):
        return f"{self.collection_name}/indexes/index_info.json"

    def __build_index_base_path(self, indexer):
        return f"{self.collection_name}/indexes/{indexer.get_name()}"

    def __batch_items(self, items, batch_size):
        return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

    def __create_manifest_file(
        self,
        update_time,
        last_modified_document_time,
        number_of_chunks,
        existing_manifest=None,
    ):
        manifest_content = self.__create_manifest_content(
            update_time,
            last_modified_document_time,
            number_of_chunks,
            existing_manifest=existing_manifest,
        )

        self.__save_json_file(manifest_content, self.__build_manifest_path())

        return manifest_content

    def __build_manifest_path(self):
        return f"{self.collection_name}/manifest.json"

    def __create_manifest_content(
        self,
        update_time,
        last_modified_document_time,
        number_of_chunks,
        existing_manifest=None,
    ):
        number_of_documents = len(
            self.persister.read_folder_files(f"{self.collection_name}/documents")
        )

        if existing_manifest:
            return {
                **existing_manifest,
                "updatedTime": update_time.isoformat(),
                "lastModifiedDocumentTime": last_modified_document_time.isoformat(),
                "numberOfDocuments": number_of_documents,
                "numberOfChunks": number_of_chunks,
            }

        return {
            "collectionName": self.collection_name,
            "updatedTime": update_time.isoformat(),
            "lastModifiedDocumentTime": last_modified_document_time.isoformat(),
            "numberOfDocuments": number_of_documents,
            "numberOfChunks": number_of_chunks,
            "reader": self.document_reader.get_reader_details(),
            "indexers": [
                {"name": indexer.get_name()} for indexer in self.document_indexers
            ],
        }

    def __save_json_file(self, content, file_path):
        self.persister.save_text_file(_json_dumps(content, indent=True), file_path)
