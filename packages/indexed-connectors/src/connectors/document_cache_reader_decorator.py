import hashlib

from loguru import logger

try:
    import orjson

    def _json_loads(data):
        return orjson.loads(data)

    def _json_dumps(data):
        return orjson.dumps(data, option=orjson.OPT_INDENT_2).decode("utf-8")
except ImportError:
    import json

    def _json_loads(data):
        return json.loads(data)

    def _json_dumps(data):
        return json.dumps(data, indent=2, ensure_ascii=False)


class CacheReaderDecorator:
    def __init__(self, reader, persister):
        self.reader = reader
        self.persister = persister

    def read_all_documents(self):
        """
        Iterates over all documents from the underlying reader, yielding each document and using a persister-backed cache to avoid re-reading or re-computing on subsequent calls.

        On a cache hit, documents are yielded from the persister's stored files; on a cache miss, documents are read from the underlying reader, saved into the persister for future calls, and yielded as they are produced.

        Returns:
            iterator: An iterator that yields each document as a deserialized JSON object (typically a dict).
        """
        cache_key = self.__build_cache_key()

        if self.persister.is_path_exists(cache_key) and self.persister.is_path_exists(
            f"{cache_key}_completed"
        ):
            logger.info(f"Cache hit during 'read_all_documents' for {cache_key}")
            for file_name in self.persister.read_folder_files(cache_key):
                yield _json_loads(
                    self.persister.read_text_file(f"{cache_key}/{file_name}")
                )
        else:
            self.persister.remove_folder(cache_key)
            self.persister.create_folder(cache_key)
            document_index = -1
            for document in self.reader.read_all_documents():
                document_index += 1
                self.persister.save_text_file(
                    _json_dumps(document),
                    f"{cache_key}/{document_index}.json",
                )

                yield document

            if document_index >= 0:
                self.persister.save_text_file("", f"{cache_key}_completed")
            else:
                # Don't mark empty results as completed — a future run
                # with the same settings should retry instead of returning
                # zero documents from cache.
                self.persister.remove_folder(cache_key)
                logger.warning(
                    "No documents produced for cache key %s; "
                    "cache not persisted so next run will retry.",
                    cache_key,
                )

    def get_number_of_documents(self):
        """
        Return the number of documents available for the underlying reader, using a completed cache when present.

        Returns:
            int: Number of documents; taken from the completed cache directory if a valid cache exists, otherwise obtained from the wrapped reader.
        """
        cache_key = self.__build_cache_key()

        if self.persister.is_path_exists(cache_key) and self.persister.is_path_exists(
            f"{cache_key}_completed"
        ):
            logger.info(f"Cache hit during 'get_number_of_documents' for {cache_key}")
            return len(self.persister.read_folder_files(cache_key))
        else:
            return self.reader.get_number_of_documents()

    def get_reader_details(self) -> dict:
        return self.reader.get_reader_details()

    def remove_cache(self):
        cache_key = self.__build_cache_key()

        self.persister.remove_folder(cache_key)
        self.persister.remove_file(f"{cache_key}_completed")

    def __build_cache_key(self):
        hash_object = hashlib.sha256(
            _json_dumps(self.reader.get_reader_details()).encode("utf-8")
        )
        return hash_object.hexdigest()
