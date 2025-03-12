import os
import shutil
from logging import getLogger
import pickle
import json
import time
from typing import Dict
from dataclasses import dataclass
import hashlib

logger = getLogger(__name__)


class CidStore:
    def __init__(self, store_path, source_hash):
        self.hash_alg = hashlib.sha224()
        self.chunk_size = 10_240  # 10 kb
        self.store_path = store_path
        self.source_hash = source_hash
        self.index: Dict[str, Cid] = {}  # Stores content id along with cid objects
        self.load_index()
        self.clear_store()

    def load_index(self):
        if not os.path.isdir(self.store_path):
            os.mkdir(self.store_path)
        if os.path.isfile(os.path.join(self.store_path, 'index.pickle')):
            with open(os.path.join(self.store_path, 'index.pickle'), 'rb') as f:
                self.index = pickle.load(f)

    def clear_store(self):
        """Check store paths against index and remove any files not present in index"""
        for path in os.listdir(self.store_path):
            full_path = os.path.join(self.store_path, path)
            if os.path.isdir(full_path):
                if path not in self.index:
                    shutil.rmtree(full_path, ignore_errors=True)
                else:
                    for dir_path, dir_names, file_names in os.walk(full_path):
                        for f in file_names:
                            if f not in self.index:
                                remove_path = os.path.join(dir_path, f)
                                os.remove(remove_path)
                        for d in dir_names:
                            if d not in self.index:
                                remove_path = os.path.join(dir_path, d)
                                shutil.rmtree(remove_path, ignore_errors=True)

    def save_index(self):
        with open(os.path.join(self.store_path, 'index.pickle'), 'wb') as f:
            pickle.dump(self.index, f)

    def add_node_dict(self, node_dict):
        """Adds node dictionary to your index. Todo: Handle all intersections between new and old nodes"""
        for node_key in node_dict:
            cid = cid_builder(node_dict[node_key])
            if cid:
                if cid.parent in self.index or cid.type == 0:
                    self.index[cid.hash] = cid
                else:  # Parent not found in index and is not a head node
                    logger.warning('Received node dictionary that could not be traced to source node')

    def add_file_node(self, data_path, name=None, parent=None):
        """Add file node to the data store. Ensure that checks have already been done to ensure that none of your
        own files are being replaced."""
        node_type = 1  # File store
        if not parent:
            parent = self.source_hash
        parent_type = self.index[parent].type
        if parent_type == 1 or parent_type == 3:  # Invalid because file cannot be child of file or file chunk
            logger.warning("Cannot add file node: parent of node cannot be a file or file chunk")
            return False  # Return early false for error
        if not name:
            name = os.path.split(data_path)[-1]  # use file name if name isn't given
        parents = self.get_parent_hashes(parent)
        parents.append(parent)  # full parent list for forming storage path
        with open(data_path, 'rb') as f:
            data = f.read()
        return self.add_node(name, parent, node_type, None, data)

    def add_node(self, name, parent, node_type, time_stamp=None, data_store: bytes = None, stored=False):
        """Blind node addition adding a node to the node dictionary and saving data to the store if present"""
        # ensure we have permission to write to this tree
        parents = self.get_parent_hashes(parent)
        parents.append(parent)
        source = parents[0]
        if source == self.source_hash:
            children = []  # Empty list will be added by regressive call if needed
            if not time_stamp:
                time_stamp = int(time.time())
            size = 0
            if data_store:  # Save data to storage path along with calculating hash
                hash_digest = self.get_data_hash(parent, data_store)
                size = len(data_store)
                stored = True
            else:  # Not a storage node, so calculate hash based on source path
                hash_digest = self.get_path_hash(parent)
            self.index[parent].children.append(hash_digest)
            self.index[hash_digest] = Cid(hash_digest, name, time_stamp, size, parent, children, stored, node_type)
            if size and node_type == 1:  # Is of type file so break into chunks
                for i, pos in enumerate(range(0, size, self.chunk_size)):
                    self.add_node(f'{name}.chunk_{i}', hash_digest, 3, time_stamp, data_store[pos:pos+self.chunk_size])
            elif size:
                with open(os.path.join(self.store_path, self.get_data_path(hash_digest)), 'wb') as f:
                    f.write(data_store)
            return hash_digest

    def get_data_path(self, node_hash):  # get data path
        """Returns the path where data associated with node should be stored"""
        path = self.store_path
        node = self.index[node_hash]
        for p in self.get_parent_hashes(node_hash):  # Calculating parent part of path
            path = os.path.join(path, self.index[p].hash)
            if not os.path.isdir(path):  # make path if none exists
                os.mkdir(path)
        path = os.path.join(path, node.hash)
        return path

    def get_path_hash(self, parent_hash):
        """Get hash associated with path to current hash to the source node"""
        hash_alg = self.hash_alg.copy()  # Hash alg for forming main file hash
        parents = self.get_parent_hashes(parent_hash)
        parents.append(parent_hash)  # full parent list for forming storage path
        hash_alg.update(''.join(parents).encode('utf8'))
        hash_digest = hash_alg.hexdigest()
        return hash_digest

    def get_data_hash(self, parent_hash, data: bytes):
        """Gets binary hash of a data node including source information"""
        hash_alg = self.hash_alg.copy()  # Hash alg for forming main file hash
        hash_alg.update(self.get_path_hash(parent_hash).encode('utf8'))
        hash_alg.update(data)
        hash_digest = hash_alg.hexdigest()
        return hash_digest

    def get_node(self, hash):
        """Get data associated with node either its information about its children, or the file chunk itself packaged
        in binary. Return nothing if no data was found"""
        if hash in self.index:
            node = self.index[hash]
            if node.type != 3:  # look for node information
                info = self.get_node_information(hash)
                if len(info) > 1:
                    return json.dumps(info)  # Return json encoded data
            else:  # Look for data chunk to return
                data = self.get_data(hash)
                return data

    def get_data(self, hash):
        """Blindly retrieve associated data"""
        node = self.index[hash]
        path = os.path.join(self.store_path, self.get_data_path(hash))
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = f.read()
            if node.hash == self.get_data_hash(node.parent, data):
                return data
            else:
                logger.warning(f'Data stored in {node.hash} did not match hash')
        else:
            node.is_stored = False

    def get_node_information(self, hash, initial_req=True):
        """Returns a dict of all node information below hash in tree"""
        node_dict = {}
        if hash in self.index:
            node = self.index[hash]
            node_dict[hash] = node.dump()
            if node.type != 1 or initial_req:  # ignore file chunks unless initial request
                for child_hash in node.children:
                    if child_hash not in node_dict:  # Ensure we don't enter a loop of references or repeat references
                        child_dict = self.get_node_information(child_hash, initial_req=False)
                        node_dict.update(child_dict)
        return node_dict

    def get_parent_hashes(self, node_hash):
        """Returns a list of parent hashes starting at source"""
        parent_hashes = []
        if node_hash in self.index:
            if self.index[node_hash].type != 0:
                parent = self.index[node_hash].parent
                parent_hashes = self.get_parent_hashes(parent)
                parent_hashes.append(parent)
        else:
            logger.warning('Could not get parent hash, parent was not in index')
        return parent_hashes

@dataclass
class Cid:
    """Class for keeping track of content ID links"""
    hash: str  # Hash of the represented node
    name: str  # name of the file
    time_stamp: int  # time stamp of the node creation
    size: int  # Size of data associated
    parent: str  # parent hash
    children: list  # children hash
    is_stored: bool  # whether file is stored locally
    type: int  # Type of the file represented {1: file, 2: dir, 0: source, 3: file data chunk}

    def dump(self):
        node_dict = {'hash': self.hash,
                     'name': self.name,
                     'time_stamp': self.time_stamp,
                     'size': self.size,
                     'parent': self.parent,
                     'children': self.children,
                     'type': self.type,
                     'is_stored': self.is_stored}
        return node_dict


def cid_builder(node_dict):
    try:
        hash = node_dict['hash']
        name = node_dict['name']
        time_stamp = node_dict['time_stamp']
        size = node_dict['size']
        parent = node_dict['parent']
        children = node_dict['children']
        node_type = node_dict['type']
        stored = node_dict['is_stored']
        cid = Cid(hash, name, time_stamp, size, parent, children, stored, node_type)
        return cid
    except KeyError:
        logger.warning("Received Node Dictionary was missing key data")
        return


if __name__ == '__main__':
    store = CidStore('../test_store', '12345')
    store.add_node_dict({'12345': {'hash': '12345', 'name': 'hermes', 'time_stamp': 123, 'size': 0, 'parent': 'root',
                                   'children': ['54321'], 'type': 0, 'is_stored': False},
                         '54321': {'hash': '54321', 'name': 'files', 'time_stamp': 123, 'size': 0,
                                   'parent': '12345', 'children': ['chunk1'], 'type': 1, 'is_stored': True},
                         'chunk1': {'hash': 'chunk1', 'name': 'file.txt.chunk', 'time_stamp': 123, 'size': 1048,
                                    'parent': '54321', 'children': [], 'type': 3, 'is_stored': True}
                         })
    print(store.get_node_information('12345'))
    print(store.get_node_information('54321'))
    print(store.get_parent_hashes('chunk1'))
    print(store.add_file_node('../README.md', 'readme.md'))
    f_hash = store.add_file_node('../test/hello.txt', 'test.txt', '12345')
    file_data = json.loads(store.get_node(f_hash))
    for hash in file_data[f_hash]['children']:
        print(store.get_node(hash))
    store.save_index()
