import json
import argparse

from main.utils.performance import log_execution_duration
from main.factories.search_collection_factory import create_collection_searcher

ap = argparse.ArgumentParser()
ap.add_argument("-collection", "--collection", required=True, help="collaction name (will be used as root folder name)")
ap.add_argument("-index", "--index", required=False, default="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2", help="index that will be used for search")
ap.add_argument("-query", "--query", required=True, help="text query for search")
ap.add_argument("-maxNumberOfResults", "--maxNumberOfResults", required=False, type=int, default=10, help="Max number of results to return")
ap.add_argument("-includeFullText", "--includeFullText", action="store_true", required=False, default=False, help="If passed - full text content will be included in the search result.")
ap.add_argument("-includeAllChunksText", "--includeAllChunksText", action="store_true", required=False, default=False, help="If passed - all chunks text content will be included in the search result.")
ap.add_argument("-includeMatchedChunksText", "--includeMatchedChunksText", action="store_true", required=False, default=False, help="If passed - matched chunks text content will be included in the search result.")
args = vars(ap.parse_args())

searcher = create_collection_searcher(collection_name=args['collection'], index_name=args['index'])

search_result = log_execution_duration(lambda: searcher.search(args['query'], 
                                                               include_text_content=args['includeFullText'], 
                                                               include_matched_chunks_content=args['includeMatchedChunksText'],
                                                               include_all_chunks_content=args['includeAllChunksText'], 
                                                               number_of_results=args['maxNumberOfResults']),
                                       identifier=f"Searching collection: {args['collection']} by query: {args['query']}")

print(json.dumps(search_result, indent=4))