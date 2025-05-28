import argparse

from main.factories.update_collection_factory import create_collection_updater

ap = argparse.ArgumentParser()
ap.add_argument("-collection", "--collection", required=True, help="collection name (will be used to determine root folder and manifest file)")
args = vars(ap.parse_args())

create_collection_updater = create_collection_updater(args['collection'])

create_collection_updater.run()