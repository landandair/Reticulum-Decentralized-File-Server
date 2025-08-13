# Reticulum-File-Server
Distributed and decentralized file server protocol utilizing the Reticulum Network Stack to handle the traffic

## Functional Overview
Currently is very proof of concept but is in bare form functional and quite advanced tool for Reticulum. 

- This service is intended to be run in the background as a service on a Reticulum node machine alongside RNS
- The service will maintain and update a hash map of both your own and other peoples files and distribute and share those files to other nodes automatically and on request
- An API is hosted by the service for interacting via a client application such as [RDFS_Explorer](https://github.com/landandair/RDFS_Explorer)
    - Other client apps can be developed and use the same api for interacting with the file server as desired to get node information, write files, request data, see the status of previous requests, and otherwise manage the data stored on the server
- The data is not stored directly in your file system but is instead stored in cryptographically tracked pieces in a data store making spoofing and faking more difficult and collisions between two otherwise identical file paths impossible
- The node that origionally sourced the image doesnt have to be present for their data and files to continue being shared in the network
    - As long as someone hosts the file, the file will remain accessible
- Long hops and jumps are avoided since the file slowly makes its way across a network and is saved at many points, recall of a file can be carried out at the nearer points instead of hopping all the way to the origional source especially if the origional source is unreliable or on a slow part of the network


## Key issues
- A severe lack of security analysis or testing leading to a requirement of only sharing and downloading files from people you trust 100%
    - If you wouldnt download and run an exe from them, dont share files with them with this method. Consider this your warning though security feedback is appreciated. 
- Lack of Scalability with the current Hash table storage method being crude and simplistic
    - It will be possible to upgrade this in the future to resolve this issue but currently it is a big problem


TODO:

api:

rns:  

store:  
- Needs conversion to sqlite

base state class: 
