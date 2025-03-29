from collections import deque

from rns_interface import RNSInterface
from cid_store import CidStore

class ServerCommandState:
    def __init__(self, rns_interface:RNSInterface, cid_store:CidStore, max_file_size=None):
        self.rns_interface = rns_interface
        self.cid_store = cid_store
        self.cid_store.set_update_callback(callback=self.updated_hash_callback)
        self.primary_req_queue = deque()
        self.auto_req_queue = deque()
        self.max_file_size = max_file_size

    def should_auto_req(self, new_hash):
        """TODO: Add a filter to only request hash on network if the metadata meets certain criteria(only use on files and
        data chunks)"""
        self.auto_req_queue.append(new_hash)

    def get_node_info(self, node_hash):
        """Get node data associated to info"""
        return self.cid_store.get_node(node_hash)

    def updated_hash_callback(self, node_hash):
        """Called when the cid storage has added any nodes from a dictionary(json file)"""
        node = self.cid_store.get_node_obj(node_hash)
        if node.type == node.TYPE_CHUNK or node.type == node.TYPE_FILE:  # Check if it is a file
            if node.size < self.max_file_size and self.max_file_size:  # Check if it is within size limits
                if not self.cid_store.check_is_stored(node.hash):  # Check if it is already stored
                    print(f"RNFS Manager: Automatically requesting {node_hash}")
                    self.rns_interface.make_hash_desire_request(node_hash)
