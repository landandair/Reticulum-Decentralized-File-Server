import argparse
import os
import time

import cid_store
from rns_interface import RNSInterface
import server_command_state
import RNS

def main(args):
    # Cid_store_args
    store_path = args.path
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

    # Make cid_store
    store = cid_store.CidStore(store_path, server_identity.hexhash, server_name)
    # Make rns interface
    rns_interface = RNSInterface(store, server_identity, allow_all=True)
    # Make main command
    server_command = server_command_state.ServerCommandState(rns_interface, store)
    try:
        print(f'Starting server using identity of: {server_identity.hexhash}')
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
    args = parser.parse_args()
    main(args)