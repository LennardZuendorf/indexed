try:
    import orjson

    def _json_loads(data):
        return orjson.loads(data)
except ImportError:
    import json

    def _json_loads(data):
        return json.loads(data)


# Upper bound on how many FAISS neighbours a doc-grouped search will fetch.
# The over-fetch (see `search()`) is what prevents a single many-chunk
# document from starving other matching documents out of the top-k (bug A5).
# FAISS's flat index is an exact brute-force search, so a larger k is cheap
# at the supported scale (<100k chunks) — this just bounds the worst case.
_OVERFETCH_CEILING = 10_000


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
        # Over-fetch the FAISS neighbour pool independently of the output
        # chunk cap so grouping-by-document isn't starved by one dominant
        # document filling the top-k (bug A5). `max_number_of_chunks` becomes
        # a hard cap on *output* chunks, applied in `__build_results`, not the
        # FAISS fetch size.
        fetch_k = max(
            max_number_of_chunks,
            min(self.indexer.get_size(), _OVERFETCH_CEILING),
        )
        scores, indexes = self.indexer.search(text, fetch_k)

        results = self.__build_results(
            scores,
            indexes,
            include_text_content,
            include_all_chunks_content,
            include_matched_chunks_content,
            max_docs=max_number_of_documents,
            max_chunks=max_number_of_chunks,
        )

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
        max_docs=None,
        max_chunks=None,
    ):
        index_document_mapping = self._get_mapping()

        result = {}
        total_chunks = 0

        for result_number in range(len(indexes[0])):
            # Once both caps are satisfied, nothing further in the (ranked)
            # pool can improve the result — stop early.
            if (
                max_docs is not None
                and len(result) >= max_docs
                and max_chunks is not None
                and total_chunks >= max_chunks
            ):
                break

            index_id = indexes[0][result_number]
            # Skip invalid indices (FAISS returns -1 when there aren't enough results)
            if index_id < 0:
                continue
            mapping = index_document_mapping[str(index_id)]
            document_id = mapping["documentId"]

            if document_id not in result:
                if max_docs is not None and len(result) >= max_docs:
                    # Doc cap reached — don't admit new documents, but keep
                    # scanning: a document already admitted may still gain
                    # matching chunks further down the ranked pool.
                    continue

                result[document_id] = {
                    "id": document_id,
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
                total_chunks += 1

                if include_all_chunks_content or include_text_content:
                    document = self.__get_document(mapping["documentPath"])

                    if include_all_chunks_content:
                        result[document_id]["allChunks"] = document["chunks"]

                    if include_text_content:
                        result[document_id]["text"] = document["text"]

            else:
                # Enrichment chunks for an already-admitted document are
                # capped by max_chunks; discovering a *new* document above is
                # never blocked by this cap (that would reintroduce A5's
                # starvation).
                if max_chunks is not None and total_chunks >= max_chunks:
                    continue

                result[document_id]["matchedChunks"].append(
                    self.__build_chunk_result(
                        mapping, scores, result_number, include_matched_chunks_content
                    )
                )
                total_chunks += 1

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
