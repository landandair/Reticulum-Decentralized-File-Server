import argparse
import os
import logging
import sys
from logging.handlers import RotatingFileHandler

import cid_store
from rns_interface import RNSInterface
import server_command_state
import RNS

logger = logging.getLogger(__name__)


def main(args):
    store_path = args.path
    max_size = args.max_file_size
    api_host = args.hostname
    api_port = args.port
    server_name = args.name
    allow_all = args.allowAll
    allowed_peers_path = args.allowedPeers
    config_path = args.config_path

    # Cid_store_args
    if not os.path.exists(store_path):
        os.mkdir(store_path)

    # Reticulum interface args
    reticulum = RNS.Reticulum(config_path)
    identity_path = os.path.join(store_path, 'rns_identity.id')  # TODO: Change this to point to rns location
    server_identity = None
    if os.path.isfile(identity_path):
        server_identity = RNS.Identity.from_file(identity_path)
    if not server_identity:
        RNS.log("No valid saved identity found, creating new...", RNS.LOG_INFO)
        server_identity = RNS.Identity()
        server_identity.to_file(identity_path)
    server_destination = RNS.Destination(
        server_identity,
        RNS.Destination.IN,
        RNS.Destination.SINGLE,
        RNSInterface.app_name,
        "receiver"
    )

    # Set up logger
    log_path = os.path.join(store_path, 'rnfs.log')
    my_handler = RotatingFileHandler(log_path, mode='w', maxBytes=5 * 1024 * 1024,
                                     backupCount=2, delay=False)
    logging.basicConfig(level=logging.DEBUG,
                format="%(asctime)s %(name)-10s %(levelname)-8s %(message)s",
                datefmt="%y-%m-%d %H:%M:%S",
                handlers=[
                    my_handler,
                    logging.StreamHandler(stream=sys.stdout)
                ])

    # Make cid_store
    store = cid_store.CidStore(store_path, server_destination.hexhash, server_name)
    # Make rns interface
    rns_interface = RNSInterface(store, server_destination, allowed_peers_path, allow_all=allow_all)
    # Make main command
    server_command = server_command_state.ServerCommandState(rns_interface, store, api_host, api_port,
                                                             max_file_size=max_size)
    for i in store.index:
        print(store.index[i])
    try:
        logger.info(f'Starting server using identity of: {server_destination.hexhash}')
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
    parser.add_argument('--port', default=8000, type=int, help='port number for api')
    parser.add_argument('--hostname', default='', type=str, help='ip to bind api to')
    parser.add_argument('--allowAll', action='store_true', help='Allow all destinations to join server('
                                                                            'Keep in mind the risks involved)')
    parser.add_argument('-a', '--allowedPeers',  default='', type=str, help='File path to list of allowed peers')
    parser.add_argument('name', type=str, help='Nickname of server')

    args = parser.parse_args()
    main(args)
