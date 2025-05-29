import os
from logging import getLogger
import pickle
import json
import time
from typing import Dict
from dataclasses import dataclass
import hashlib

logger = getLogger(__name__)


class CidStore:
    def __init__(self, store_path, source_hash, source_name, callback=None):
        self.hash_alg = hashlib.sha224()
        self.chunk_size = 10_240  # 10 kb
        self.store_path = store_path
        self.source_hash = source_hash
        self.source_name = source_name
        self.index: Dict[str, Cid] = {}  # Stores content id along with cid objects
        self.callback = callback  # must be a function(cid_store)
        self.load_index()
        self.clear_store()

    def load_index(self):
        if not os.path.isdir(self.store_path):
            os.mkdir(self.store_path)
        if os.path.isfile(os.path.join(self.store_path, 'index.pickle')):
            with open(os.path.join(self.store_path, 'index.pickle'), 'rb') as f:
                self.index = pickle.load(f)
        node = self.get_node_obj(self.source_hash)
        if not node:
            self.index[self.source_hash] = Cid(self.source_hash, self.source_name, int(time.time()), 0, 'root', [], True, Cid.TYPE_SRC)
        else:
            node.name = self.source_name

    def clear_store(self):
        """Check store paths against index and remove any files not present in index"""
        for path in os.listdir(self.store_path):
            full_path = os.path.join(self.store_path, path)
            if os.path.isdir(full_path):
                for dir_path, dir_names, file_names in os.walk(full_path):
                    for f in file_names:
                        if f not in self.index:
                            remove_path = os.path.join(dir_path, f)
                            os.remove(remove_path)

    def check_is_stored(self, hash):
        """Update storage status of node and all child nodes in store. Call before delivering node info"""
        node = self.get_node_obj(hash)
        if node:
            if node.type != Cid.TYPE_CHUNK:  # Check all children present if not chunk
                stored = True
                if not node.children and node.type == Cid.TYPE_FILE:  # File is missing chunks so is not stored
                    stored = False
                for child in node.children:
                    child_stored = self.check_is_stored(child)
                    if not child_stored:  # if any children are false the node isnt stored
                        stored = False
            else:  # Check for file existence
                stored = os.path.isfile(self.get_data_path(node.hash))
            node.is_stored = stored
            return stored
        else:  # No node exists
            return False

    def save_index(self):
        with open(os.path.join(self.store_path, 'index.pickle'), 'wb') as f:
            pickle.dump(self.index, f)

    def add_data(self, hash, data: bytes):
        """Adds node data gained in response from request"""
        node = self.get_node_obj(hash)
        if node and self.get_parent_hashes(hash):
            source = self.get_parent_hashes(hash)
            """TODO: Make it so you can add node to index without it already being there"""
            # Add data only if it doesn't conflict with our data
            if self.is_storage_hash(hash):
                if hash == self.get_data_hash(node.parent, data, include_source=False):
                    self.add_node(node.name, node.parent, node.type, node.time_stamp, data, stored=True)
                else:
                    logger.warning(
                        f"Expected data hash of {hash} but got {self.get_data_hash(node.parent, data, include_source=False)} instead.")
            elif source[0] != self.source_hash:  # Try to decode as a json store and load the dictionary
                data_dict = json.loads(data)
                self.add_node_dict(data_dict)
        else:
            data_dict = json.loads(data)
            self.add_node_dict(data_dict)

    def add_node_dict(self, node_dict):
        """Adds node dictionary to your index. Todo: Handle all intersections between new and old nodes"""
        for node_key in node_dict:
            cid = cid_builder(node_dict[node_key])
            if cid:
                if cid.hash not in self.index:  # TODO: Handle possible changes in node information
                    self.index[cid.hash] = cid
                    self.check_is_stored(cid.hash)
                    self.send_update_callback(cid.hash)
                else:  # TODO: Check if what is in the index is older or of a more reliable source
                    logger.warning('Received node dictionary that was already in source node')
            # TODO: Mop up after node addition by removing all dereference nodes
        self.save_index() # Save index after modifying it

    def set_update_callback(self, callback):
        self.callback = callback

    def send_update_callback(self, updated_hash):
        if self.callback:
            self.callback(updated_hash)

    def add_file_path(self, data_path, name=None, parent=None):
        """Add file node to the data store. Ensure that checks have already been done to ensure that none of your
        own files are being replaced."""
        node_type = Cid.TYPE_FILE  # File store
        if not parent:
            parent = self.source_hash
        parent_type = self.get_node_obj(parent).type
        if parent_type == Cid.TYPE_FILE or parent_type == Cid.TYPE_CHUNK:  # Invalid because file cannot be child of file or file chunk
            logger.warning("Cannot add file node: parent of node cannot be a file or file chunk")
            return False  # Return early false for error
        if not name:
            name = os.path.split(data_path)[-1]  # use file name if name isn't given
        with open(data_path, 'rb') as f:
            data = f.read()
        return self.add_node(name, parent, node_type, None, data)

    def add_file(self, file_name, data, parent=None):
        if not parent:
            parent = self.source_hash
        parent_node = self.get_node_obj(parent)
        if parent_node:
            parent_type = parent_node.type
            if parent_type == Cid.TYPE_FILE or parent_type == Cid.TYPE_CHUNK:  # Invalid because file cannot be child of file or file chunk
                logger.warning("Cannot add file node: parent of node cannot be a file or file chunk")
                return False  # Return early false for error
            if self.source_hash not in self.get_parent_hashes(parent) and self.source_hash != parent:
                logger.warning(f"Cannot add file node: Source node not a parent of '{parent}'")
                return False  # Return early false for error
            return self.add_node(file_name, parent, Cid.TYPE_FILE, None, data)
        else:
            logger.warning("Cannot add file node: Parent node not found")
            return False  # Return early false for error

    def add_dir(self, name, parent=None):
        if not parent:
            parent = self.source_hash
        parent_node = self.get_node_obj(parent)
        if parent_node:
            parent_type = parent_node.type
            if parent_type == Cid.TYPE_FILE or parent_type == Cid.TYPE_CHUNK:  # Invalid because file cannot be child of file or file chunk
                logger.warning("Cannot add file node: parent of node cannot be a file or file chunk")
                return False  # Return early false for error
            if self.source_hash not in self.get_parent_hashes(parent) and self.source_hash != parent:
                logger.warning(f"Cannot add file node: Source node not a parent of '{parent}'")
                return False  # Return early false for error
            return self.add_node(name, parent, Cid.TYPE_DIR, None, None)
        else:
            logger.warning("Cannot add file node: Parent node not found")
            return False  # Return early false for error


    def add_node(self, name, parent, node_type, time_stamp=None, data_store: bytes = None, stored=False):
        """Blind node addition adding a node to the node dictionary and saving data to the store if present"""
        # ensure we have permission to write to this tree
        children = []  # Empty list will be added by regressive call if needed
        if not time_stamp:
            time_stamp = int(time.time())
        size = 0
        if data_store:  # Save data to storage path along with calculating hash
            hash_digest = self.get_data_hash(parent, data_store,
                                             node_type != Cid.TYPE_CHUNK)  # Check if it is a file chunk when getting hash
            size = len(data_store)
            stored = True
        else:  # Not a storage node, so calculate hash based on source path
            hash_digest = self.get_path_hash(parent)
        if hash_digest not in self.get_node_obj(parent).children:
            self.get_node_obj(parent).children.append(hash_digest)
        self.index[hash_digest] = Cid(hash_digest, name, time_stamp, size, parent, children, stored, node_type)
        if size and node_type == Cid.TYPE_FILE:  # Is of type file so break into chunks
            for i, pos in enumerate(range(0, size, self.chunk_size)):
                self.add_node(f'{name}.chunk_{i}', hash_digest, Cid.TYPE_CHUNK, time_stamp,
                              data_store[pos:pos + self.chunk_size])
        elif size:
            with open(self.get_data_path(hash_digest), 'wb') as f:
                f.write(data_store)
        return hash_digest

    def get_data_path(self, node_hash):  # get data path
        """Returns the path where data associated with node should be stored"""
        path = os.path.join(self.store_path, 'store')
        node = self.get_node_obj(node_hash)
        if node:
            # for p in self.get_parent_hashes(node_hash):  # Calculating parent part of path
            #     path = os.path.join(path, self.index[p].hash)
            if not os.path.isdir(path):  # make path if none exists
                os.mkdir(path)
            path = os.path.join(path, node.hash)
            return path
        return None

    def get_path_hash(self, parent_hash):
        """Get hash associated with path to current hash to the source node"""
        hash_alg = self.hash_alg.copy()  # Hash alg for forming main file hash
        parents = self.get_parent_hashes(parent_hash)
        parents.append(parent_hash)  # full parent list for forming storage path
        hash_alg.update(''.join(parents).encode('utf8'))
        hash_digest = hash_alg.hexdigest()
        return hash_digest

    def get_data_hash(self, parent_hash, data: bytes, include_source=True):
        """Gets binary hash of a data node including source information if desired(is file pointer)"""
        hash_alg = self.hash_alg.copy()  # Hash alg for forming main file hash
        if include_source:
            hash_alg.update(self.get_path_hash(parent_hash).encode('utf8'))
        hash_alg.update(data)
        hash_digest = hash_alg.hexdigest()
        return hash_digest

    def get_node_obj(self, hash):
        if hash in self.index:
            return self.index[hash]
        return None

    def get_node(self, hash):
        """Get data associated with node either its information about its children, or the file chunk itself packaged
        in binary. Return nothing if no data was found"""
        if not hash:
            return json.dumps(self.get_sources())
        self.check_is_stored(hash)  # Update all storage status for nodes
        node = self.get_node_obj(hash)
        logger.info(f'Generating data for: {node}')
        if node:
            if node.type != Cid.TYPE_CHUNK:  # look for node information
                info = self.get_node_information(hash)
                if len(info) >= 1:
                    return json.dumps(info)  # Return json encoded data
                return None
            else:  # Look for data chunk to return
                data = self.get_data(hash)
                return data
        return None

    def get_data(self, hash):
        """Blindly retrieve associated chunk data"""
        node = self.get_node_obj(hash)
        if node:
            path = self.get_data_path(hash)
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    data = f.read()
                if node.hash == self.get_data_hash(node.parent, data, include_source=False):
                    return data
                else:
                    logger.warning(f'Data stored in {node.hash} did not match hash')
                    return None
            else:
                node.is_stored = False
                return None
        return None

    def get_node_information(self, hash, initial_req=True):
        """Returns a dict of all node information below hash in tree"""
        node_dict = {}
        node = self.get_node_obj(hash)
        if node:
            node_dict[hash] = node.dump()
            if node.type != Cid.TYPE_FILE or initial_req:  # ignore file chunks unless initial request
                for child_hash in node.children:
                    if child_hash not in node_dict:  # Ensure we don't enter a loop of references or repeat references
                        child_dict = self.get_node_information(child_hash, initial_req=False)
                        node_dict.update(child_dict)
        return node_dict

    def get_sources(self):
        """Send list of sources to directory"""
        node_dict = {}
        for hash in self.index:
            node = self.get_node_obj(hash)
            if node:
                if node.type == Cid.TYPE_SRC:
                    node_dict[hash] = node.dump()
        return node_dict

    def is_storage_hash(self, hash_str):
        """Checks to see if its a chunk hash"""
        node = self.get_node_obj(hash_str)
        if node:
            if node.type == Cid.TYPE_CHUNK:
                return True
        return False

    def get_parent_hashes(self, node_hash):
        """Returns a list of parent hashes starting at source"""
        parent_hashes = []
        node = self.get_node_obj(node_hash)
        if node:
            if node.type != Cid.TYPE_SRC:
                parent = node.parent
                parent_hashes = self.get_parent_hashes(parent)
                parent_hashes.append(parent)
        else:
            logger.warning('Could not get parent hash, parent was not in index')
        return parent_hashes

    def get_children(self, node_hash, include_chunks=False):
        """Gets all children associated with node"""
        child_hashes = []
        node = self.get_node_obj(node_hash)
        if node:
            if node.type != Cid.TYPE_FILE or include_chunks:  # exclude chunks as children
                for c in node.children:
                    child_hashes.append(c)
                    child_children = self.get_children(c, include_chunks=include_chunks)
                    child_hashes.extend(child_children)
        return child_hashes

    def get_source_checksum(self, source_hash):
        children = self.get_children(source_hash)
        children_data = str(sorted(children)).encode('utf8')
        data_hash = self.get_data_hash(b'', children_data, include_source=False)
        return data_hash

    def remove_hash(self, hash_id):
        node = self.get_node_obj(hash_id)
        if node:
            if node.type != node.TYPE_SRC:
                self.index.pop(hash_id)
                self.clean_data()
                return True
            else:
                logger.warning("User attempted to delete root node")
        return False

    def clean_data(self):
        for hash_id in tuple(self.index.keys()):
            node = self.get_node_obj(hash_id)
            if node:
                if node.parent not in self.index and node.type != node.TYPE_SRC:
                    if node.type == node.TYPE_CHUNK:
                        path = self.get_data_path(hash_id)
                        os.remove(path)
                    self.remove_hash(hash_id)

    def clean_hash_data(self, hash_id):
        node = self.get_node_obj(hash_id)
        if node:
            if node.parent not in self.index:
                for child in self.get_children(hash_id, include_chunks=True):
                    self.clean_hash_data(child)
                self.remove_hash(hash_id)


@dataclass
class Cid:
    """Class for keeping track of content ID links"""
    # Constants
    TYPE_FILE = 1
    TYPE_DIR = 2
    TYPE_SRC = 0
    TYPE_CHUNK = 3
    # Attributes
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
        stored = False
        cid = Cid(hash, name, time_stamp, size, parent, children, stored, node_type)
        return cid
    except KeyError:
        logger.warning("Received Node Dictionary was missing key data")
        return


if __name__ == '__main__':
    store = CidStore('store', '12345', 'hermes')
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
    print(file_data)
    for hash in file_data[f_hash]['children']:
        print(store.get_node(hash))
    store.save_index()
    store2 = CidStore('store_2', '123456', 'hermes2')
    store2.add_node_dict(json.loads(store.get_node('12345')))
    print(store2.get_node('12345'))
    print(store.get_node('12345'))
