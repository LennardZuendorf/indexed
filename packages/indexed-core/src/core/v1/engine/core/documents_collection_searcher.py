try:
    import orjson

    def _json_loads(data):
        return orjson.loads(data)
except ImportError:
    import json

    def _json_loads(data):
        return json.loads(data)


class DocumentCollectionSearcher:
    def __init__(self, collection_name, indexer, persister):
        self.collection_name = collection_name
        self.indexer = indexer
        self.persister = persister
        self._index_document_mapping = None
        self._document_cache = {}

    def _get_mapping(self):
        """Lazy-load and cache the index-document mapping."""
        if self._index_document_mapping is None:
            indexes_base_path = f"{self.collection_name}/indexes"
            self._index_document_mapping = _json_loads(
                self.persister.read_text_file(
                    f"{indexes_base_path}/index_document_mapping.json"
                )
            )
        return self._index_document_mapping

    def search(
        self,
        text,
        max_number_of_chunks=15,
        max_number_of_documents=None,
        include_text_content=False,
        include_all_chunks_content=False,
        include_matched_chunks_content=False,
    ):
        scores, indexes = self.indexer.search(text, max_number_of_chunks)

        results = self.__build_results(
            scores,
            indexes,
            include_text_content,
            include_all_chunks_content,
            include_matched_chunks_content,
        )
        if max_number_of_documents:
            results = results[:max_number_of_documents]

        return {
            "collectionName": self.collection_name,
            "indexerName": self.indexer.get_name(),
            "results": results,
        }

    def __build_results(
        self,
        scores,
        indexes,
        include_text_content,
        include_all_chunks_content,
        include_matched_chunks_content,
    ):
        index_document_mapping = self._get_mapping()

        result = {}

        for result_number in range(0, len(indexes[0])):
            index_id = indexes[0][result_number]
            # Skip invalid indices (FAISS returns -1 when there aren't enough results)
            if index_id < 0:
                continue
            mapping = index_document_mapping[str(index_id)]

            if mapping["documentId"] not in result:
                result[mapping["documentId"]] = {
                    "id": mapping["documentId"],
                    "url": mapping["documentUrl"],
                    "path": mapping["documentPath"],
                    "matchedChunks": [
                        self.__build_chunk_result(
                            mapping,
                            scores,
                            result_number,
                            include_matched_chunks_content,
                        )
                    ],
                }

                if include_all_chunks_content or include_text_content:
                    document = self.__get_document(mapping["documentPath"])

                    if include_all_chunks_content:
                        result[mapping["documentId"]]["allChunks"] = document["chunks"]

                    if include_text_content:
                        result[mapping["documentId"]]["text"] = document["text"]

            else:
                result[mapping["documentId"]]["matchedChunks"].append(
                    self.__build_chunk_result(
                        mapping, scores, result_number, include_matched_chunks_content
                    )
                )

        return list(result.values())

    def __build_chunk_result(
        self, mapping, scores, result_number, include_matched_chunks_content
    ):
        return {
            "chunkNumber": mapping["chunkNumber"],
            "score": float(scores[0][result_number]),
            **(
                {
                    "content": self.__get_document(mapping["documentPath"])["chunks"][
                        mapping["chunkNumber"]
                    ]
                }
                if include_matched_chunks_content
                else {}
            ),
        }

    def __get_document(self, document_path):
        """Load a document with caching to avoid repeated disk I/O."""
        if document_path not in self._document_cache:
            self._document_cache[document_path] = _json_loads(
                self.persister.read_text_file(document_path)
            )
        return self._document_cache[document_path]
