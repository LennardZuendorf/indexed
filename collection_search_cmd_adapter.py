import json
import argparse

from main.utils.performance import log_execution_duration
from main.factories.search_collection_factory import create_collection_searcher

ap = argparse.ArgumentParser()
ap.add_argument("-collection", "--collection", required=True, help="collaction name (will be used as root folder name)")
ap.add_argument("-index", "--index", required=False, default="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2", help="index that will be used for search")
ap.add_argument("-query", "--query", required=True, help="text query for search")
args = vars(ap.parse_args())

searcher = create_collection_searcher(collection_name=args['collection'], index_name=args['index'])

search_result = log_execution_duration(lambda: searcher.search(args['query']),
                                       identifier=f"Searching collection: {args['collection']} by query: {args['query']}")

print(json.dumps(search_result, indent=4))