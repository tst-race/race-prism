# **Resilient Anonymous Communication for Everyone (RACE) Prism (Network Manager) Guide**

## **Table of Contents**
- [**Terminology**](#terminology)
- [**Introduction**](#introduction)
  * [**Design Goals**](#design-goals)
  * [**Security Considerations**](#security-considerations)
- [**Scope**](#scope)
  * [**Audience**](#audience)
  * [**Environment**](#environment)
  * [**License**](#license)
  * [**Additional Reading**](#additional-reading)
    + [Prism-specific Documentation](#prism-specific-documentation)
    + [General RACE Documentation](#general-race-documentation)
- [**Implementation Overview**](#implementation-overview)
- [**How To Build**](#how-to-build)
    + [**Known Limitations**](#known-limitations)
- [**How To Run**](#how-to-run)
  * [**Custom Config Generation Arguments**](#custom-config-generation-arguments)
- [**Troubleshooting**](#troubleshooting)

<br></br>

## **Terminology**
*add implementation-specific terms and acronyms*
<br></br>

## **Introduction**
PRISM is a RACE network manager plugin that provides construction and maintenance of an overlay network of servers to facilitate secure anonymous communication for clients.
See [Conceptual Overview of PRISM](doc/Concept.md) for more details.
</br>

### **Design Goals**
Provide secure anonymous messaging for clients across a covert and resilient overlay network.

### **Security Considerations**
This plugin is a research prototype and has not been the subject of an independent security audit or extensive external testing.

<br></br>

## **Scope**
This developer guide covers the PRISM development model, building artifacts, running, and troubleshooting.  It is structured this way to first provide context, associate attributes/features with source files, then guide a developer through the build process.  

</br>

### **Audience**
Technical/developer audience.

### **Environment**
Supports x86 and arm64 Linux and Android hosts as a Python plugin with additional binary dependencies.

### **License**
Licensed under the APACHE 2.0 license, see LICENSE file for more information.

### **Additional Reading**

#### Prism-specific Documentation
* [Conceptual Overview of PRISM](doc/Concept.md)
* [Code Walkthrough](doc/Code.md)
* [Boneh-Franklin IBE Implementation](./bfibe/README.md)
* [RIB Plugin](./rib/README.md)


#### General RACE Documentation
* [RACE Quickstart Guide](https://github.com/tst-race/race-quickstart/blob/main/README.md)

* [What is RACE: The Longer Story](https://github.com/tst-race/race-docs/blob/main/what-is-race.md)

* [Developer Documentation](https://github.com/tst-race/race-docs/blob/main/RACE%20developer%20guide.md)

* [RIB Documentation](https://github.com/tst-race/race-in-the-box/tree/2.6.0/documentation)

<br></br>

## **Implementation Overview**
See the [Code Walkthrough](doc/Code.md) for details.

<br></br>

## **How To Build**
Ensure Python3.8+ and Docker are installed and available, then run `build.sh`. This will produce a `kit` directory that can be used in a RACE deployment. 

</br>

#### **Known Limitations**
Prism has a maximum client plaintext message size to prevent over-large messages congesting the network. It is set to 2,000 Bytes by default.

<br></br>

## **How To Run**
Include in a RACE deployment as the NetworkManager by adding the following arguments to a `rib deployment create` command:
```
--network-manager-kit=<kit source for prism>
```
*Note:* the deployment will need at least 6 servers to function reliably in order to provide sufficient servers to operate as mixing and dropbox servers.

### **Custom Config Generation Arguments**
PRISM can take a number of optional arguments for generation of initial deployment configurations that can change how the overlay operates and how channels are used. In particular, channels are assigned a "tag" that informs PRISM what types of messages to use the channel for. There are default values for existing RACE channels, but these can be overridden and ___if you are using a new channel then tags must be provided for PRISM to use it___.

When running a deployment using RiB there are options that can be passed after creation to customize Comms running. In order to have clean configs when doing a deployment create make sure to add ``--no-config-gen` to it. Then before running an up/start you can create new configs running: `rib deployment local config gen`
For PRISM, these argumetns take the form of `--tags<channel name>=role1,role2...` arguments to the `--network-manager-custom-args` argument of a `deployment config generate` command. E.g.
```
rib-use local <deployment name>
deployment config generate --network-manager-custom-args="--tagstwoSixIndirectCpp=mpc,lsp --tagobfs="
```
This would tell PRISM to use twoSixIndirectCpp for `mpc` and `lsp` messages (server-to-server control and messaging traffic) that it would not normally use it for. It also _removes_ default tags from obfs which causes it to not be tagged for use with any messages.

The tags are:
- `mpc`: intra-dropbox committee traffic used for multiparty computation
- `lsp`: inter-server control traffic
- `ark`: periodic overlay status messages, must have at least a 3KB MTU
- `uplink`: client-to-server message sending
- `downlink`: server-to-client message forwarding
- `epoch`: special epoch-change notifications

<br></br>

## **Troubleshooting**
PRISM takes some time to "warm-up" because clients must receive ARK messages bearing information about the overlay network and then establish client-to-server links into the network. When this has happened can be viewed in a RIB deployment via either OpenTracing or the network visualization graph.

In OpenTracing any given race-client service will show a series of Link Created events immediately on startup. After some time, they will accumulate ark message events, one or more poll request events, and a Link Loaded event; once these have occurred the client should be ready to send and receive messages.

<br></br>
