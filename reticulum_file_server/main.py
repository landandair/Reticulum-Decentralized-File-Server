import argparse
import os
import logging
from logging.handlers import RotatingFileHandler

import cid_store
from rns_interface import RNSInterface
import server_command_state
import RNS

logger = logging.getLogger(__name__)


def main(args):
    store_path = args.path
    max_size = args.max_file_size
    # Cid_store_args
    if not os.path.exists(store_path):
        os.mkdir(store_path)
    server_name = 'test'

    # Reticulum interface args
    config_path = None
    reticulum = RNS.Reticulum(config_path)
    identity_path = os.path.join(store_path, 'rns_identity.id')  # TODO: Change this to point to rns location
    server_identity = None
    if os.path.isfile(identity_path):
        server_identity = RNS.Identity.from_file(identity_path)
    if not server_identity:
        RNS.log("No valid saved identity found, creating new...", RNS.LOG_INFO)
        server_identity = RNS.Identity()
        server_identity.to_file(identity_path)

    # Set up logger
    log_path = os.path.join(store_path, 'rnfs.log')
    my_handler = RotatingFileHandler(log_path, mode='w', maxBytes=5 * 1024 * 1024,
                                     backupCount=2, delay=False)
    logging.basicConfig(level=logging.DEBUG,
                format="%(asctime)s %(name)-10s %(levelname)-8s %(message)s",
                datefmt="%y-%m-%d %H:%M:%S",
                handlers=[
                    my_handler,
                    logging.StreamHandler()
                ])

    # Make cid_store
    store = cid_store.CidStore(store_path, server_identity.hexhash, server_name)
    # Make rns interface
    rns_interface = RNSInterface(store, server_identity, allow_all=True)
    # Make main command
    server_command = server_command_state.ServerCommandState(rns_interface, store, max_size)
    try:
        logger.info(f'Starting server using identity of: {server_identity.hexhash}')
        # store.add_file_node('../README.md', 'readme.md')
        # store.add_file_node('../test/hello.txt', 'test.txt')
        while True:
            pass  # Put a waiting loop here with basic announce functionality
            inp = input()
            if inp:
                print("Announcing")
                rns_interface.send_announce()
    finally:
        store.save_index()  # ensure index gets saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Reticulum file server')
    parser.add_argument('-p', '--path', default='store', type=str, help='Path to storage directory')
    parser.add_argument('-m', '--max_file_size', default=5000, type=int, help='max size of files automatically '
                                                                              'accepted in bytes')
    parser.add_argument('-c', '--config_path', default=None, type=str, help='Path to RNS config')
    parser.add_argument('name', type=str, help='Nickname of server')
    args = parser.parse_args()
    main(args)
