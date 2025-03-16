"""rns_interface.py
Main purpose is to share and request files over the network and to maintain an index of what files are currently
available.

Request process:  Requesting a specific node hash
1. Announce(RH): Make an announcement from your destination containing the hash you wish to have
2. Announce(RP or NP): Source destination first and later other servers if the server or another client doesnt respond in a
    timely fashion respond with a hash present flag along with the hash they have
3. Link: Requestor forms Link to the desired source either at random or from the original source if available
4. Link(Identify): Requestor sends identity
5. Link(Packet): Requestor confirms hash desired
6. Link(Resource): Source sends resource associated with hash

Update Process: adding a new file or directory
1. Announce(NH): Announcement containing hash of node added to index
2. Announce(RH): Requestor(s) requests hash of the new segment added if not already in index

Periodic Checksum: Used for maintaining consistency across server instances ensuring propagation of all nodes
1. Announce(CS): Check sum of destination source index(sort supplied hashes combine them and calculate hash)
2. Announce(RH): Requestor(s) requests hash of the destination and updates index accordingly
"""
import RNS
from cid_store import CidStore, Cid


class RNSInterface:
    app_name = "Reticulum-File-Server"
    request_hash_id = "RH"  # Request hash: Request hash
    resource_present_id = "RP"  # Resource: Segment of a file
    node_present_id = "NP"  # Node present: non-file segment hash
    new_hash_id = "NH"  # New node hash present: non-file-segment node information
    check_sum_id = "CS"  # Checksum of whole destination index check against local copy

    def __init__(self, cid_store: CidStore, config_path=None):
        self.hash_requests = []  # List of hashes requested from network
        self.cid_store = cid_store  # Store of data
        self.currently_linked = False  # Maintain whether we are currently connected to a peer Used to limit incoming
        # and outgoing requests
        self.allowed_peers = []  # Always allowed peers who we will host files from
        self.banned_peers = []  # Never allowed peers who we will deny hosting files or requests from

        self.reticulum = RNS.Reticulum(config_path)
        self.server_identity = RNS.Identity()
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
        # TODO: Generate resource associated with hash
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

    def resource_complete(self, resource: RNS.Resource):
        """TODO: Save resource away as it was requested"""
        if resource.status == RNS.Resource.COMPLETE:
            try:  # Save the file
                pass
                # file = open(saved_filename, "wb")
                # file.write(resource.data.read())
                # file.close()
            except:
                RNS.log(f'RNSFS: Save Error')
        else:
            RNS.log(f'RNSFS: resource Error')

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
