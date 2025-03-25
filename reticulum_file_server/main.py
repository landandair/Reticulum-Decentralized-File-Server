import argparse
import cid_store
from rns_interface import RNSInterface
import RNS

def main(args):
    store_path = args.path
    config_path = None
    reticulum = RNS.Reticulum(config_path)
    server_identity = RNS.Identity()
    store = cid_store.CidStore(store_path, server_identity.hexhash)
    rns_interface = RNSInterface(store, server_identity, allow_all=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Reticulum file server')
    parser.add_argument('-p', '--path', default='store', type=str, help='Path to storage directory')
    args = parser.parse_args()
    main(args)