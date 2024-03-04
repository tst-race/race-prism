# Conceptual Overview of PRISM

PRISM is a secure, anonymous end-to-end messaging system designed to resist corruption by an adversary who may shut down or compromise server nodes in its network. By "secure", we mean that the adversary should not be able to identify the contents of messages sent over the network. By "anonymous", we mean that the adversary should not be able to identify which users are conversing with each other.

## Background - Underlying Technologies

PRISM is built on two core technologies: Identity-based Encryption and Multi-Party Computation.

**Identity-based Encryption** is a system for key escrow that removes the need for one party to learn another party's public key before encrypting messages to them. We implement the system introduced in [Identity-based Encryption from the Weil Pairing](https://crypto.stanford.edu/~dabo/papers/bfibe.pdf) by Dan Boneh and Matthew Franklin, and extend it to allow multiple parties to hold fragments of the system secret such that no single party has the ability to decrypt arbitrary messages.

In this system, a committee of servers cooperatively generate a set of public parameters as well as individual secret keys. A client will request a fragment of their private encryption key from each of these servers, which it will then assemble into a full private key. A client may then encrypt a message to any other client by computing a function of the recipient's identity and the public parameters, without requiring prior knowledge of the recipient's public key.

Our message storage and retrieval servers ("Dropboxes") use two **multi-party computation** components: [Shamir's secret sharing](https://en.wikipedia.org/wiki/Shamir%27s_secret_sharing) and the [BGW multiplication protocol](https://crypto.stanford.edu/pbc/notes/crypto/bgw.html). Shamir's secret sharing allows a piece of data to be split up into several "shares", and later be reconstructed from some subset of those shares. This scheme has two important properties: 1) if you take the shares of a number X and add them to the respective shares of a number Y, you will wind up with a set of shares of (X+Y), and 2) the BGW protocol can be used to mutiply two secret numbers by operating on their shares without revealing the original secrets, constructing shares of (X•Y).

## Client Identities and Pseudonyms

A client's "identity" is a human-readable text string, such as "bob@example.com". Their pseudonym is constructed by appending a salt to their identity and applying the SHA-256 hash function. This salt may be a function of the current date and time, to ensure that pseudonyms are difficult to link across time.

## Server Roles

PRISM servers are divided into two different roles: Dropbox and Emix (short for "Entry mixer"). 

### Dropboxes

Dropbox servers work in committes of 4, and securely store messages until they are requested for retrieval. When a message is sent to a dropbox committee, both the message and the pseudonym of the recipient are secret shared using Shamir's secret sharing, and each share is encrypted for a different committee member. This ensures that compromising a single member of the committee will not reveal the content or recipient of any stored messages.

A client wishing to check if a Dropbox has any messages for them creates secret shares of their current pseudonym, encrypted for each committee member, and sends a "poll request" consisting of these shares and a return address, encrypted for one member of the committee. To check if a stored message matches a poll request, the committee subtracts the shares of the stored pseudonym from the shares of the poll pseudonym. If both pseudonyms are the same, this will result in shares of 0. The committee then multiplies the resulting shares by the shares of a large random number `R`, collets those shares, and reveals the result. If the result is 0, then the message is forwarded to the return address and deleted. If the result is nonzero, no member of the committee has learned anything about either pseudonym.

Each Dropbox committee is assigned an index. Clients are assigned to one or more dropbox indices based on their current pseudonym.

### Emix

Emix servers obfuscate the origin of a message from the dropbox where it is to be stored, by acting as a three layer onion route. As long as at least one Emix on the route is honest, the final Emix learns nothing about the origin of the message. To mitigate temporal linking of messages, Emixes delay messages by a random number of seconds chosen from the Poisson distribution.

## Sortition and Epochs

To reduce the long-term value of server compromise, server roles are regularly shuffled using cryptographic sortition. Each server computes a verifiable random function (VRF) and derives its new role from the output of that function using public parameters.

## ARKs

Servers broadcast a message containing their pseudonym, role, proof of correct sortition, and public key. This is called the "Announcement of Role and Keys" or ARK for short.

## Lifecycle of a Client Message

When Alice wants to send a message to Bob, she first encrypts the message using a randomly generated 256-bit AES key. She then encrypts this key for Bob using Identity-based Encryption and Bob's identity. She computes Bob's current pseudonym and determines which Dropboxes Bob is polling based on which ARK messages she has heard from servers. She creates secret shares of Bob's pseudonym and the encrypted message, and further encrypts these for each member of the dropbox committee(s). She then picks a series of Emix servers to route the message through, and wraps the message in onion layers encrypted for each of the chosen servers, and sends the message to the outermost server.

Meanwhile, Bob regularly sends poll requests (similarly onion routed) to each of his assigned dropboxes. When one of these poll requests matches Alice's message, it will be forwarded to Bob.

## Client Registration

A new client entering the system for the first time needs to obtain a private key and public parameters from a registration committee in order to communicate with other clients who use the same committee. We are not strongly opinionated about how many of these committees should exist or how they should be run. 
