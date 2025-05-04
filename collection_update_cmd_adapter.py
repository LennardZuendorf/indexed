import argparse

from main.factories.update_collection_factory import create_collection_updator

ap = argparse.ArgumentParser()
ap.add_argument("-collection", "--collection", required=True, help="collaction name (will be used to determine root folder and manifest file)")
args = vars(ap.parse_args())

create_collection_updator = create_collection_updator(args['collection'])

create_collection_updator.run()