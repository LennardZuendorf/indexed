import os
import argparse

from main.sources.jira.jira_cloud_document_reader import JiraCloudDocumentReader
from main.sources.jira.jira_cloud_document_converter import JiraCloudDocumentConverter
from main.factories.create_collection_factory import create_collection_creator

ap = argparse.ArgumentParser()
ap.add_argument("-url", "--url", required=True, help="Jira Cloud base url (e.g., https://your-domain.atlassian.net)")
ap.add_argument("-jql", "--jql", required=True, help="jql query to get tickets for indexing")
ap.add_argument("-collection", "--collection", required=True, help="collection name (will be used as root folder name)")
ap.add_argument("-indexers", "--indexers", required=False, default=["indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"], help="list on indexer names", nargs='+')
args = vars(ap.parse_args())

email = os.environ.get('ATLASSIAN_EMAIL')
api_token = os.environ.get('ATLASSIAN_TOKEN')

if not email or not api_token:
    raise ValueError("Both 'ATLASSIAN_EMAIL' and 'ATLASSIAN_TOKEN' environment variables must be provided for Jira Cloud.")

# Validate that the URL is a Cloud URL
if not args['url'].endswith('.atlassian.net'):
    raise ValueError("URL must be a Jira Cloud URL (ending with .atlassian.net). For Server/Data Center Jira, use jira_collection_create_cmd_adapter.py instead.")

jira_cloud_document_reader = JiraCloudDocumentReader(base_url=args['url'],
                                                     query=args['jql'],
                                                     email=email,
                                                     api_token=api_token)

jira_cloud_document_converter = JiraCloudDocumentConverter()

jira_cloud_collection_creator = create_collection_creator(collection_name=args['collection'],
                                                          indexers=args['indexers'],
                                                          document_reader=jira_cloud_document_reader,
                                                          document_converter=jira_cloud_document_converter)

jira_cloud_collection_creator.run() 