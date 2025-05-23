from collections import deque
from logging import getLogger
from json import dumps

from rns_interface import RNSInterface
from cid_store import CidStore
from file_server_api import start_server_thread

logger = getLogger(__name__)

class ServerCommandState:
    def __init__(self, rns_interface:RNSInterface, cid_store:CidStore, host:str, port:int, max_file_size=-1):
        self.rns_interface = rns_interface
        self.cid_store = cid_store
        self.cid_store.set_update_callback(callback=self.updated_hash_callback)
        self.primary_req_queue = deque()
        self.auto_req_queue = deque()
        self.max_file_size = max_file_size
        self.api_ip = host
        self.api_port = port
        start_server_thread(self)

    def get_address(self):
        return self.api_ip, self.api_port

    def should_auto_req(self, new_hash):
        """TODO: Add a filter to only request hash on network if the metadata meets certain criteria(only use on files and
        data chunks)"""
        self.auto_req_queue.append(new_hash)

    def get_node_info(self, node_hash):
        """Get node data associated to info"""
        info = self.cid_store.get_node(node_hash)
        if not info:
            info = dumps({})
        return info

    def get_file_data(self, node_hash):
        node = self.cid_store.get_node_obj(node_hash)
        if node and self.cid_store.check_is_stored(node_hash):
            if node.type == node.TYPE_FILE:
                data = b''
                for child in node.children:
                    data_chunk = self.cid_store.get_node(child)
                    if data_chunk:
                        data += data_chunk
                if node.hash == self.cid_store.get_data_hash(node.parent, data, include_source=True):
                    return data
                else:
                    logger.warning(f"File hash for {node.name} does not match data")
        elif node:
            for child in self.cid_store.get_children(node_hash, include_chunks=True):
                if not self.cid_store.check_is_stored(child):
                    self.rns_interface.make_hash_desire_request(child)
        else:
            self.rns_interface.make_hash_desire_request(node_hash)
        return None

    def get_node_name(self, node_hash):
        node = self.cid_store.get_node_obj(node_hash)
        if node:
            return node.name

    def get_src_dest(self):
        return self.cid_store.source_hash

    def upload_file(self, file_name, file_data, parent=None):
        self.cid_store.add_file(file_name, file_data, parent)

    def make_dir(self, name, parent=None):
        self.cid_store.add_dir(name, parent)

    def delete_node(self, id):
        return self.cid_store.remove_hash(id)

    def updated_hash_callback(self, node_hash):
        """Called when the cid storage has added any nodes from a dictionary(json file)"""
        node = self.cid_store.get_node_obj(node_hash)
        if node.type == node.TYPE_CHUNK or node.type == node.TYPE_FILE:  # Check if it is a file
            logger.debug(f'learned about new file node of Size-{node.size}')
            if node.size < self.max_file_size or self.max_file_size == -1:  # Check if it is within size limits
                if not self.cid_store.check_is_stored(node.hash):  # Check if it is already stored
                    logger.info(f"RNFS Manager: Automatically requesting {node_hash}")
                    self.rns_interface.make_hash_desire_request(node_hash)
