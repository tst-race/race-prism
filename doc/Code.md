# PRISM Code Walkthrough

This document is intended as a high-level overview of the layout of the PRISM codebase and its major components. A general conceptual overview of the system can be found in the [Concept](./Concept.md) document. Paths are specified relative to the root of this repository.

## Common Functionality (`prism/common`)

Features used from multiple places in the PRISM system (e.g. clients and servers) live in `prism/common`. These include:

* configuration (`prism/common/config`)
* cryptography (`prism/common/crypto`)
* networking (`prism/common/transport`)
* sortition (`prism/common/epoch` and `prism/common/vrf`)
* logging (`prism/common/logging.py`)

and various utility libraries.

Of particular note is `prism/common/message.py`, which contains the data structures used for sending messages between different PRISM components. We use [CBOR](https://cbor.io/) as our serialization format. CBOR combines the flexibility of JSON with a more compact binary representation suitable for transmission over bandwidth-limited networks.

### Configuration

We use the [Dynaconf](https://www.dynaconf.com/) library to load our configuration. Defaults for clients, servers, and general defaults for everyone are loaded from `.toml` files in `prism/common/config`.

### Cryptography

We use Elliptic Curve Diffie-Hellman key exchange and Curve25519 for public key cryptography between clients and servers and between pairs of servers.

We implement the Boneh-Franklin Identity-Based Encryption system with some extensions as a [C shared library](../bfibe) in `bfibe`, with Python bindings using CFFI in `prism/common/crypto/ibe`.

Shamir's secret sharing is implemented in [prism/common/crypto/secretsharing/shamir.py](../prism/common/crypto/secretsharing/shamir.py).

### Networking

Our networking model is designed to match closely with the RACE view of networking, where a collection of "channels" can be used to create "links", which can open "connections" to send and receive messages. These links may be uni- or bi-directional, uni- or multi-cast, and direct or indirect. Links have addresses, which can be loaded by other network nodes to send or receive on that link.

The interfaces of Transports/Channels/Links are defined in [prism/common/transport/transport.py](../prism/common/transport/transport.py) and implemented separately by the [CommsTransport](../rib/prism/rib/connection/CommsTransport.py) class.

### Concurrency

Our codebase heavily uses the [Trio](https://trio.readthedocs.io/en/stable/) Python library for [structred concurrency](https://en.wikipedia.org/wiki/Structured_concurrency).

## Client (`prism/client`)

The PrismClient class is designed to be embedded in a larger program (for example, some server roles embed a client). It needs to be supplied with a Transport, a MessageDelegate (an object whose `message_received` method is called when a new message is received), a `StateStore` to persist state (note: state pesistence is not fully implemented yet). Its operation is split into a handful of subtasks that run asynchronously. The primary subtasks are: `receive_task`, which handles messages received from the networking layer, `send_task`, which maintains a queue of outgoing messages and tracks their status, and `poll_task`, which polls assigned dropboxes for new messages at regular intervals.

### Web Interface

The client can expose a web interface and REST API as an additional subtask using the FastAPI framework if configured. The frontend interface is implemented in SvelteJS in the [client-frontend](../client-frontend) directory. The compiled output from the Svelte framework is copied into `prism/client/web/static`.

## Server (`prism/server`)

### Epochs

To facilitate a smooth transition between epochs, the top level functionality of the server is to run a set of epoch processes in parallel. The very first epoch in a deployment is called "Genesis", and the server gets some extra configuration information about its role and neighbors from configuration. In subsequent epochs, role and network neighbors are determined by sortition.

Epoch changes happen when an EpochCommand signal is processed. In testing/development, these signals come from a centralized command and control infrastructure such as race-in-the-box, but in a real production deployment they would be triggered automatically at regular intervals based on a known schedule.

### Routing

Inter-server messaging is handled by an implementation of the Router interface, which declares methods for sending messages to a single server (or client), flooding them to all servers, or broadcasting to a set of connected clients or whiteboards. The default implementation is the LinkStateRouter class, which manages a link-state routing protocol and message flooding system.

## Config Generator (`prism/config`)

Generates client and server configuration files for test deployments. Can be specialized for different environments by subclassing the Deployment and Range classes and implementing a new entry point that configures the above with any environment-specific details before invoking the `run()` function from `prism/config/generate.py`.

## Monitoring (`prism/monitor`)

A text-based system monitor that reports on server status and message delivery for test deployments. Usually invoked through the `prt monitor` command.

## RACE Integration (`rib/prism/`)

Contains all RACE-specific code in the codebase.

### Plugin (`rib/prism/rib`)

Implements client and server plugin classes and the CommsTransport network layer that translates between the RACE SDK and PRISM's Transport abstraction.

### Config Generator (`rib/prism/rib_config`)

RACE-specific config generator code.

### Prism RIB Toolkit (`rib/prism/ribtools`)

Contains tooling for building/testing/running the RACE-integrated version of PRISM. If you install the `prism-rib` package (`pip -e rib` in the root directory of the repository), this can be accessed with the `prt` command. Each `prt` command is represented by a class in the `rib/prism/ribtools/commands` directory, with documentation found in the docstrings.

### Dashboard (`rib/prism/dashboard`)

An ElasticSearch-based dashboard that fulfills a similar role as the monitor, but scales to larger deployments where the filesystem of each node is not so easily accessed. Uses OpenTracing events generated by clients and servers.
