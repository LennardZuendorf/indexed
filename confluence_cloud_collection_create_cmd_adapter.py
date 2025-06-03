import os
import argparse

from main.sources.confluence.confluence_cloud_document_reader import ConfluenceCloudDocumentReader
from main.sources.confluence.confluence_cloud_document_converter import ConfluenceCloudDocumentConverter
from main.factories.create_collection_factory import create_collection_creator

ap = argparse.ArgumentParser()
ap.add_argument("-url", "--url", required=True, help="Confluence Cloud base url (e.g., https://your-domain.atlassian.net)")
ap.add_argument("-cql", "--cql", required=True, help="confluence query to get pages for indexing")
ap.add_argument("-collection", "--collection", required=True, help="collection name (will be used as root folder name)")
ap.add_argument("-indexers", "--indexers", required=False, default=["indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"], help="list on indexer names", nargs='+')
ap.add_argument("-readOnlyFirstLevelComments", "--readOnlyFirstLevelComments", action="store_true", required=False, default=False, help="Confluence has hierarchical comments, first level comments are read by default, but for other ones additional call is needed what can slowdown the process. Pass this argument to read only first level comments and have better performance.")
args = vars(ap.parse_args())

email = os.environ.get('ATLASSIAN_EMAIL')
api_token = os.environ.get('ATLASSIAN_TOKEN')

if not email or not api_token:
    raise ValueError("Both 'ATLASSIAN_EMAIL' and 'ATLASSIAN_TOKEN' environment variables must be provided for Confluence Cloud.")

# Validate that the URL is a Cloud URL
if not args['url'].endswith('.atlassian.net'):
    raise ValueError("URL must be a Confluence Cloud URL (ending with .atlassian.net). For Server/Data Center Confluence, use confluence_collection_create_cmd_adapter.py instead.")

confluence_cloud_document_reader = ConfluenceCloudDocumentReader(base_url=args['url'],
                                                                 query=args['cql'],
                                                                 email=email,
                                                                 api_token=api_token,
                                                                 read_all_comments=(not args['readOnlyFirstLevelComments']))
confluence_document_converter = ConfluenceCloudDocumentConverter()

confluence_cloud_collection_creator = create_collection_creator(collection_name=args['collection'],
                                                                indexers=args['indexers'],
                                                                document_reader=confluence_cloud_document_reader,
                                                                document_converter=confluence_document_converter)

confluence_cloud_collection_creator.run() 