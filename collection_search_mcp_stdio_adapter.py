import json
import argparse

from mcp.server.fastmcp import FastMCP

from main.factories.search_collection_factory import create_collection_searcher

mcp = FastMCP("documents-search")

ap = argparse.ArgumentParser()
ap.add_argument("-collection", "--collection", required=True, help="collaction name (will be used as root folder name)")
ap.add_argument("-index", "--index", required=False, default="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2", help="index that will be used for search")
ap.add_argument("-maxNumberOfChunks", "--maxNumberOfChunks", required=False, type=int, default=100, help="Max number of text chunks in result")
ap.add_argument("-maxNumberOfDocuments", "--maxNumberOfDocuments", required=False, type=int, default=None, help="Max number of documents in result")
args = vars(ap.parse_args())

searcher = create_collection_searcher(collection_name=args['collection'], index_name=args['index'])

@mcp.tool(name=f"search_{args['collection']}", description="Search documents in the collection")
def search_documents(query: str) -> str:
    search_results = searcher.search(query, 
                                     max_number_of_chunks=args['maxNumberOfChunks'], 
                                     max_number_of_documents=args['maxNumberOfDocuments'], 
                                     include_matched_chunks_content=True)

    return json.dumps(search_results, indent=4)
    

if __name__ == "__main__":
    mcp.run(transport='stdio')