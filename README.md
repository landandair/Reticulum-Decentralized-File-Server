# Reticulum-File-Server
Distributed and decentralized file server protocol utilizing the Reticulum Network Stack to handle the traffic

TODO:

api:  
- needs to add files to store and query store for values
Call up to base to fulfill requests
- needs read access to what the rns interface is doing
 call up to base to fulfill requests
- needs to be able to request whole files or request from interface if the file cant be accessed
Call up to base with a request and it returns data if it has it none if it made a request or already made it

rns:  
- needs decicions and desires
a queue of requests to service ideally
- needs to notify base state about the desire list and progress
method call to get state if that is requested by api

store:  
- needs to notify base state of state changes
- Need method to search for child hash to generate data chunk node from data and a hash

base state class: 
- needs to hold onto a standby queue for requested hashes and caching auto-requests
- needs to determine if a new node in store meets standards for being cached and add it to standby queue
- needs to determine how to get a file the api requests
- needs to deliver api request node information