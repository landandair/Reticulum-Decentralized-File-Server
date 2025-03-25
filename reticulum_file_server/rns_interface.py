"""rns_interface.py
Main purpose is to share and request files over the network and to maintain an index of what files are currently
available.

Request process:  Requesting a specific node hash
1. Announce(RH): Make an announcement from your destination containing the hash you wish to have
2. Announce(RP or NP): Source destination first and later other servers if the server or another client doesnt respond in a
    timely fashion respond with a hash present flag along with the hash they have
3. Request: Requestor forms Link to the desired source either at random or from the original source if available
5. Response: Requestor confirms hash desired and sends a resource in response

Update Process: adding a new file or directory
1. Announce(NH): Announcement containing hash of node added to index
2. Announce(RH): Requestor(s) requests hash of the new segment added if not already in index

Periodic Checksum: Used for maintaining consistency across server instances ensuring propagation of all nodes
1. Announce(CS): Check sum of destination source index(sort supplied hashes combine them and calculate hash)
2. Announce(RH): Requestor(s) requests hash of the destination and updates index accordingly
"""
import time
from threading import Thread
import random
from logging import getLogger
import RNS
from cid_store import CidStore

logger = getLogger(__name__)

class RNSInterface:
    app_name = "Reticulum-File-Server"
    REQUEST_HASH_ID = "RH"  # Request hash: Request hash
    NODE_PRESENT_ID = "NP"  # Node present: non-file segment hash
    NEW_HASH_ID = "NH"  # New node hash present: non-file-segment node information
    CHECKSUM_ID = "CS"  # Checksum of whole destination index check against local copy

    def __init__(self, cid_store: CidStore, server_identity: RNS.Identity, allow_all=False):
        self.hash_requests = []  # List of hashes requested from network
        self.cid_store = cid_store  # Store of data
        self.currently_linked = False  # Maintain whether we are currently connected to a peer Used to limit incoming
        # and outgoing requests
        self.allowed_peers = []  # Always allowed peers who we will host files from
        self.allow_all = allow_all
        self.banned_peers = []  # Never allowed peers who we will deny hosting files or requests from
        # hash translation map list of requested hashes and a list of identities who can provide it
        self.desired_hash_translation_map = {}
        self.request_id_to_hash = {}
        self.max_allowed_attempts = 5

        self.server_identity = server_identity
        self.server_destination = RNS.Destination(
            self.server_identity,
            RNS.Destination.IN,
            RNS.Destination.SINGLE,
            self.app_name,
            "receiver"
        )
        self.server_destination.set_link_established_callback(self.client_connected)
        # We register a request handler for handling incoming
        # requests over any established links.
        self.server_destination.register_request_handler(
            "RH",
            response_generator=self.request_handler,
            allow=RNS.Destination.ALLOW_ALL
        )
        self.broadcast_dest = RNS.Destination(None,
                                              RNS.Destination.IN,
                                              RNS.Destination.PLAIN,
                                              self.app_name,
                                              "broadcast"
                                              )
        self.broadcast_dest.set_packet_callback(self.broadcast_handler)

        announce_handler = AnnounceHandler(self.handle_announce,
                                           aspect_filter="Reticulum-File-Server.receiver"
                                           )
        # register the announce handler with Reticulum this will let us know when announces arrive
        RNS.Transport.register_announce_handler(announce_handler)

    def client_connected(self, link: RNS.Link):
        """A Request from another peer on the network. Check their id and req. packet before forming resource"""
        # Expecting a request of a specific hash we have in our index along with an identity to check against trusted
        link.set_link_closed_callback(self.client_disconnected)
        if self.currently_linked:
            link.teardown()  # Deny request outright
        else:
            self.currently_linked = True

    def request_handler(self, path, data, request_id, link_id, remote_identity: RNS.Identity, requested_at):
        """Check if the link has been identified, if it has, assume the message is a request."""
        hash_str = data.decode('utf8')
        RNS.log(f"Processing request from client for {hash_str}")
        # TODO: Check if user is identified/allowed to make request in index
        return self.cid_store.get_node(hash_str)

    def client_disconnected(self, link: RNS.Link):
        """TODO: Determine the cause of the cut adjust accordingly"""
        print(f'{link.status}: link cut')
        if link.teardown_reason == RNS.Link.TIMEOUT:
            RNS.log("The link timed out, exiting now")
        elif link.teardown_reason == RNS.Link.DESTINATION_CLOSED:
            RNS.log("The link was closed by the server, exiting now")
        else:
            RNS.log("Link closed, exiting now")
        self.currently_linked = False

    def handle_announce(self, destination_hash, announced_identity: RNS.Identity, app_data):
        """TODO: Handle incoming id packets sorted by what they are. Make decision on low priority requests or
        schedule announces into the future using threads"""
        RNS.log(
            "Received an announce from " +
            RNS.prettyhexrep(destination_hash)
        )
        if app_data:
            RNS.log(
                "The announce contained the following app data: " +
                app_data.decode("utf-8")
            )

    def broadcast_handler(self, data: bytes, packet: RNS.Packet):
        """Breakdown types of data broadcast and then store data or respond accordingly"""
        decomposed = breakdown_broadcast_data(data.decode('utf8'), 2, len(self.server_destination.hexhash))
        if decomposed:
            prefix, source, hash = decomposed
            if prefix == self.REQUEST_HASH_ID.encode('utf8'):  # This is a request of data
                self.handle_hash_request(source, hash)
            elif prefix == self.NODE_PRESENT_ID.encode('utf8'):  # This is an announcement that a resource is present
                self.handle_node_present(source, hash)
            elif prefix == self.NEW_HASH_ID.encode('utf8'):  # This is an announcement of a new node
                self.handle_new_hash(source, hash)
            elif prefix == self.CHECKSUM_ID.encode('utf8'):  # This is a checksum of a source
                self.handle_checksum(source, hash)

    def handle_hash_request(self, source, hash):
        """see if we have the data in our stores and respond if we do"""
        logger.info(f'RNFS: {source} requested {hash} from network')
        node = self.cid_store.get_node_obj(hash)
        if node:  # We have the node
            if self.cid_store.check_is_stored(hash) or node.type != 3:
                logger.info(f'RNFS: We have {hash} send response according to random chance + source')
                source = self.cid_store.get_parent_hashes(hash)[0]
                delay = 30 + random.random() * 30  # Between 30 and 60 seconds of delay
                if source == self.cid_store.source_hash:
                    delay = 0  # No delay if we are source
                data = (self.NODE_PRESENT_ID + self.server_destination.hexhash + hash).encode('utf8')
                self.send_future_broadcast(data, delay)

    def handle_node_present(self, source, hash):
        """See if we wanted the node and don't have it"""
        if hash in self.desired_hash_translation_map:  # See if we wanted it
            sources, _, _ = self.desired_hash_translation_map[hash]
            sources.append(source)  # Append the sources to dictionary

    def handle_new_hash(self, source, hash):
        """For now, always request new hashes"""
        if source in self.allowed_peers or (source not in self.banned_peers and self.allow_all):
            self.make_hash_desire_request(hash)

    def handle_checksum(self, source, hash):
        """See if the checksum is valid for the source, if not, make a desire request for the source"""
        if self.cid_store.get_source_checksum(source) != hash:
            self.make_hash_desire_request(source)

    def make_hash_desire_request(self, hash_str: str):
        """TODO: format announce to request hash presence on network move away from announces"""
        self.server_destination.announce(app_data=(self.request_hash_id + self.server_destination.hexhash + hash_str).encode('utf8'))
        if hash_str not in self.desired_hash_translation_map:
            self.desired_hash_translation_map[hash_str] = ([], 0, time.time())
            RNS.log(f'RNSFS: Requesting presence of hash in network')
        else:
            RNS.log('RNSFS: Already requested this hash on network')

    def make_hash_req(self, hash_str, target_identity: RNS.Identity):
        """Create destination for server, form a link, and make a request, this is blocking"""
        server_destination = RNS.Destination(
            target_identity,
            RNS.Destination.OUT,
            RNS.Destination.SINGLE,
            self.app_name,
            "receiver"
        )
        # And create a link
        link = RNS.Link(server_destination)
        # We'll set up functions to inform the
        # user when the link is established or closed
        link.set_link_established_callback(self.client_disconnected)
        link.set_link_closed_callback(self.client_disconnected)
        while not link:
            time.sleep(.1)
        receipt = link.request('RH',
                     data=hash_str.encode('utf8'),
                     response_callback=self.got_response_data,
                     failed_callback=self.failed_response
                     )
        if receipt:
            self.request_id_to_hash[receipt.get_request_id()] = hash_str

    def got_response_data(self, response: RNS.RequestReceipt):
        request_id = response.get_request_id()
        hash_str = self.request_id_to_hash[request_id]
        response = response.get_response()
        if response:
            self.cid_store.add_data(hash_str, response)
            self.request_id_to_hash.pop(request_id)
        response.link.teardown()

    def failed_response(self, response: RNS.RequestReceipt):
        RNS.log("The request " + RNS.prettyhexrep(response.request_id) + " failed.")
        response.link.teardown()

    def service_desired_hash_list(self):
        """Thread to service the desired hash dictionary"""
        while True:
            time.sleep(1)
            while self.currently_linked:
                time.sleep(1)
            made_request = False
            for hash in self.desired_hash_translation_map:
                sources, attempts, next_allowed_time = self.desired_hash_translation_map[hash]
                if time.time() > next_allowed_time and not made_request:
                    if sources:  # If sources have been announced request from the source
                        target_identity = sources.pop(0)
                        sources.append(target_identity)  # Move to back of line
                        self.make_hash_req(hash, target_identity)
                    else:  # make the next desire request
                        self.make_hash_desire_request(hash)
                    attempts += 1
                    next_allowed_time = time.time() + 60  # Wait a time before restarting
                    self.desired_hash_translation_map[hash] = (sources, attempts, next_allowed_time)
                elif attempts > self.max_allowed_attempts:
                    self.desired_hash_translation_map.pop(hash)

    def send_future_broadcast(self, data:bytes, delay):
        thread = Thread(target=self.delayed_broadcast, args=[data, delay], daemon=True)
        thread.start()

    def delayed_broadcast(self, data:bytes, delay: float):
        """Schedule a delay into the future, use a thread for this"""
        time.sleep(delay)
        packet = RNS.Packet(self.broadcast_dest,
                            data,
                            create_receipt=False)
        packet.send()

class AnnounceHandler:
    def __init__(self, received_announce_callback, aspect_filter=None):
        self.aspect_filter = aspect_filter
        self.callback = received_announce_callback

    # This method will be called by Reticulums Transport
    # system when an announce arrives that matches the
    # configured aspect filter. Filters must be specific,
    # and cannot use wildcards.
    def received_announce(self, destination_hash, announced_identity, app_data):
        self.callback(destination_hash, announced_identity, app_data)

def breakdown_broadcast_data(data: str, prefix_len=2, source_len=9):
    if len(data) > prefix_len+source_len:
        prefix = data[0:prefix_len]
        source = data[prefix_len: prefix_len+source_len]
        req_hash = data[prefix_len+source_len:]
        return prefix, source, req_hash
