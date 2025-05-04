import os
import argparse

from main.sources.confluence.confluence_document_reader import ConfluenceDocumentReader
from main.sources.confluence.confluence_document_converter import ConfluenceDocumentConverter
from main.factories.create_collection_factory import create_collection_creator

ap = argparse.ArgumentParser()
ap.add_argument("-url", "--url", required=True, help="confluence base url")
ap.add_argument("-cql", "--cql", required=True, help="confluence query to get tickets for label adding")
ap.add_argument("-collection", "--collection", required=True, help="collaction name (will be used as root folder name)")
ap.add_argument("-indexers", "--indexers", required=False, default=["indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"], help="list on indexer names", nargs='+')
ap.add_argument("-readOnlyFirstLevelComments", "--readOnlyFirstLevelComments", action="store_true", required=False, default=False, help="Confluence has hierarchical comments, first level comments are read by default, but for other ones additional call is needed what can slowdown the process. Pass this argument to read only first level comments and have better performace.")
args = vars(ap.parse_args())

token = os.environ.get('CONF_TOKEN')
login = os.environ.get('CONF_LOGIN')
password = os.environ.get('CONF_PASSWORD')

if not token and (not login or not password):
    raise ValueError("Either 'token' ('CONF_TOKEN' env variable) or both 'login' ('CONF_LOGIN' env variable) and 'password' ('CONF_PASSWORD' env variable) must be provided.")

confluence_document_reader = ConfluenceDocumentReader(base_url=args['url'],
                                                      query=args['cql'],
                                                      token=token,
                                                      login=login, 
                                                      password=password,
                                                      read_all_comments=(not args['readOnlyFirstLevelComments']))
confluence_document_converter = ConfluenceDocumentConverter()

confluence_collection_creator = create_collection_creator(collection_name=args['collection'],
                                                          indexers=args['indexers'],
                                                          document_reader=confluence_document_reader,
                                                          document_converter=confluence_document_converter)

confluence_collection_creator.update_collection()