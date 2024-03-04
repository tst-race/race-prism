#  Copyright (c) 2019-2023 SRI International.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
from __future__ import annotations

import itertools
import math
import networkx as nx
import random
from typing import Dict, List, Optional, Set

from prism.common.vrf.octets import i2bytes
from prism.common.vrf.distribution import VRFDistribution, VRFConfig
from prism.common.vrf.sortition import VRFSortition
from prism.common.vrf.vrf import VRF_keyGen
from prism.config.config import Configuration
from prism.config.environment.enclave import Enclave
from prism.config.environment.link import Link
from prism.config.error import ConfigError
from prism.config.node.client import Client
from prism.config.salt import optimize_salt
from prism.config.ibe.ibe import IBE
from prism.config.node.node import Node
from prism.config.node.server import Dropbox, Emix, Server, MPCDropbox, ClientRegistration, Dummy
from prism.config.topology.graph import build_graph, server_diameter


class Range:
    enclaves: Dict[str, Enclave]
    nodes: Dict[str, Node]
    links: List[Link]
    graph: Optional[nx.Graph]

    def __init__(self, nodes):
        def enclave_key(n: Node) -> str:
            return n.enclave

        self.nodes = nodes
        self.enclaves = {
            enclave_name: Enclave(enclave_name, list(enclave_members))
            for enclave_name, enclave_members in itertools.groupby(sorted(nodes.values(), key=enclave_key), enclave_key)
        }

    @property
    def clients(self) -> List[Client]:
        return [node for node in self.nodes.values() if isinstance(node, Client)]

    @property
    def servers(self) -> List[Server]:
        return [node for node in self.nodes.values() if isinstance(node, Server)]

    def servers_with_role(self, role: type):
        return [server for server in self.servers if server.is_role(role)]

    def unclaimed_servers(self) -> List[Server]:
        return [server for server in self.servers if server.unclaimed()]

    def claim_server(self) -> Optional[Server]:
        unclaimed = self.unclaimed_servers()
        if not unclaimed:
            return None

        node = unclaimed[0]
        node.claim()
        return node

    def claim_committee(self, size: int) -> List[Server]:
        enclaves = sorted(self.enclaves.values(), reverse=True, key=lambda e: len(list(e.unclaimed_servers())))
        best_enclave = enclaves[0]
        committee = list(itertools.islice(best_enclave.unclaimed_servers(), size))

        if len(committee) < size:
            return []

        for node in committee:
            node.claim()

        return committee

    def genesis_dummies(self, config: Configuration, ibe: IBE):
        """Assign all roles (except bootstrapping) to EMIX and connect in ring topology, setting this up for
           first epoch switch."""
        servers = self.servers

        # Step 0. Add the client registration committee, if bootstrapping is enabled
        if config.bootstrapping:
            reg_committee = servers[:config.ibe_shards]
            servers = servers[config.ibe_shards:]
            for idx, member in enumerate(reg_committee):
                member.role = ClientRegistration(ibe=ibe, index=idx)

        for i, server in enumerate(servers):
            server.role = Emix()

        self.limit_onion_layers(config)
        config.topology = "RING"

    def perform_sortition(self, config: Configuration, ibe: IBE):
        """Assign roles using cryptographic sortition to each server node in the range.

        Constraints:
        1. There must be at least one EMIX
        2. There must be at least one viable Dropbox (single-server or MPC committee) per pseudonym range.
        3. If bootstrapping, use one server for Client Registration.

        """
        servers = self.servers

        # Step 0. Add the client registration committee, if bootstrapping is enabled
        if config.bootstrapping:
            reg_committee = servers[:config.ibe_shards]
            servers = servers[config.ibe_shards:]
            for idx, member in enumerate(reg_committee):
                member.role = ClientRegistration(ibe=ibe, index=idx)

        # Step 1. Generate keys for all remaining servers:
        vrf_keys = {server: VRF_keyGen() for server in servers}
        print(f" ~~~ VRF Step 1: Generated {len(vrf_keys)} RSA keys for servers.")

        # Step 2. Create role distribution:
        vrf_config = VRFConfig.from_config(config.server_common)
        role_distribution, committees = VRFDistribution.role_distribution(vrf_config)
        roles = {role_name: set() for role_name in role_distribution.roles}
        print(f" ~~~ VRF Step 2: Generated probability distribution with {len(role_distribution.roles)} role names")

        # Step 3. Perform actual sortition (up to a number of times)
        sortition = VRFSortition(role_distribution)
        attempt = 0
        config_error = ""
        committee_size = 1 if config.vrf_dropbox_ss else 3
        for attempt in range(config.vrf_config_attempts):
            if vrf_config.seed:
                random.seed(vrf_config.seed)
            roles = {role: set() for role in roles.keys()}
            for server, key in vrf_keys.items():
                server.tags.update({"vrf_key": key})  # keep track of VRF key for further use
                alpha = i2bytes(random.randint(0, 2 ** 256 - 1), 2048)
                role, _ = sortition.sort_and_prove(key, alpha)
                roles[role].add(server)

            # Step 4. Check for viability.
            config_error = ""
            if len(roles['EMIX']) < 1:
                config_error = "No EMIX selected in this round"
                continue
            assert sum([len(server_set) for server_set in roles.values()]) == len(servers)
            viable_committees_per_range = {n_range: config.server_common['vrf_m_replicas']
                                           for n_range in range(1, config.server_common['vrf_n_ranges'] + 1)}
            for role, (n_range, m_replica) in committees.items():
                if len(roles[role]) < committee_size:
                    print(f"     Attempt #{attempt + 1}: " +
                          f"Non-viable committee {role}: {[s.name for s in roles[role]]}")
                    viable_committees_per_range[n_range] -= 1
                    if viable_committees_per_range[n_range] < 1:
                        config_error = f"Not enough viable DROPBOX committees for pseudonym range={n_range}"
                        break
            if not config_error:
                break  # configuration is good.

        printable = {role: len(server_set) for role, server_set in roles.items()}
        print(f" ~~~ VRF Step 3: Sortition (attempt #{attempt + 1} of {config.vrf_config_attempts}) = {printable}")
        if config_error:
            raise ConfigError(config_error)

        # Apply winning sortition: first DROPBOX MPC committees, second EMIX, third OFF
        prior_db_per_client = config.prism_common.get("dropboxes_per_client", 0)
        if prior_db_per_client and prior_db_per_client > 1 and config.server_common["vrf_db_index_from_range_id"]:
            print(f"WARNING: Configuration asks for prism.dropboxes_per_client={prior_db_per_client} " +
                  f"and server.vrf_db_index_from_range_id=True, which will force prism.dropboxes_per_client=1!")
        for role, (n_range, m_replica) in committees.items():
            # determine DROPBOX index for clients; two cases:
            # 1) if vrf_db_index_from_range_id = True: simply map (n_range - 1) = db_index so that the
            #    replicas take care of redundancy (transparent to clients) and set prism.dropboxes_per_client = 1
            # 2) otherwise: spread all dropbox indices over [0; (n_ranges * m_replicas) - 1]
            if config.server_common["vrf_db_index_from_range_id"]:
                dropbox_index = (n_range - 1)
                config.client_common["dropboxes_per_client"] = 1
            else:
                dropbox_index = (n_range - 1)*config.server_common['vrf_m_replicas'] + (m_replica - 1)
            mpc_committee = sorted(roles[role])
            for party_id, server in zip(range(len(mpc_committee)), mpc_committee):
                # if committee size = 1 then use single-server dropbox, otherwise MPC:
                if committee_size == 1:
                    server.role = Dropbox(dropbox_index)
                    server.tags["dropbox_index"] = dropbox_index
                elif len(mpc_committee) < committee_size or party_id > committee_size:
                    # mark defunct or overhead DROPBOX servers as DUMMY
                    server.role = Dummy()
                else:
                    server.role = MPCDropbox(dropbox_index, party_id, mpc_committee[:4])
                    if party_id == 0:
                        server.tags.update({"mpc_leader": True, "dropbox_index": dropbox_index})
                    server.tags.update(
                        {"mpc_committee": dropbox_index,
                         "mpc_party_id": party_id,
                         "mpc_committee_members": mpc_committee[:4]}
                    )
        for server in roles['EMIX']:
            server.role = Emix()
        for server in roles['OFF']:
            server.role = Dummy()

        # print servers' roles count in Step 4...
        final_roles = {server.role.role_name: 0 for server in self.servers}
        for server in self.servers:
            final_roles[server.role.role_name] += 1
        print(f" ~~~ VRF Step 4: Final role sortition (attempt #{attempt + 1}) = {final_roles}")

        self.limit_onion_layers(config)

        if config.server_common["vrf_b_db_emix"] >= 0:
            # signal that we also use VRF for topology creation
            config.topology = "VRF"

    def pick_dropbox_parameters(self, config: Configuration):
        """
        Fill in any missing values for dropbox parameters based on range size.
        """
        server_count = len(self.servers)

        if config.ss_dropbox_ratio is None and config.mpc_dropbox_ratio is None:
            if server_count < config.mpc_committee_size:
                config.mpc_dropbox_ratio = 0.0
                config.ss_dropbox_ratio = 0.5
            else:
                config.mpc_dropbox_ratio = (config.mpc_committee_size - 1) / config.mpc_committee_size
                config.ss_dropbox_ratio = 0.0
        elif config.ss_dropbox_ratio is None and config.mpc_dropbox_ratio > 0:
            config.ss_dropbox_ratio = 0.0
        elif config.mpc_dropbox_ratio is None and config.ss_dropbox_ratio > 0:
            config.mpc_dropbox_ratio = 0.0

    def assign_roles(self, config: Configuration, ibe: IBE):
        """Assign roles to each node in the range.

        Constraints:
        1. There must be at least one EMIX and at least one Dropbox.
        2. MPC Dropbox committees must not be split across enclaves.
        3. Dropbox roles take up at most config.mpc_dropbox_ratio + config.ss_dropbox_ratio percent of all server nodes.
        """
        servers = self.servers
        dropbox_index = 0

        # Step 1. Determine server node targets.
        self.pick_dropbox_parameters(config)
        mpc_committees = max(
            math.ceil(config.mpc_dropbox_ratio),
            math.floor(len(servers) * config.mpc_dropbox_ratio / config.mpc_committee_size)
        )
        ss_count = math.floor(len(servers) * config.ss_dropbox_ratio)

        if ss_count + mpc_committees == 0:
            raise ConfigError("Configuration does not allow any dropboxes.")

        # Step 2. Assign MPC dropbox roles
        for _ in range(mpc_committees):
            mpc_committee = self.claim_committee(config.mpc_committee_size)
            if not mpc_committee:
                break

            mpc_committee[0].tags["mpc_leader"] = True
            mpc_committee[0].tags["dropbox_index"] = dropbox_index

            for party_id, server in zip(range(len(mpc_committee)), mpc_committee):
                server.role = MPCDropbox(dropbox_index, party_id, mpc_committee)
                server.tags.update(
                    {"mpc_committee": dropbox_index, "mpc_party_id": party_id, "mpc_committee_members": mpc_committee}
                )

            dropbox_index += 1

        # Step 3. Assign SS dropbox roles
        for _ in range(ss_count):
            server = self.claim_server()
            if not server:
                break
            server.role = Dropbox(dropbox_index)
            server.tags["dropbox_index"] = dropbox_index
            dropbox_index += 1

        # Step 4. Add the client registration committee, if bootstrapping is enabled
        unclaimed = self.unclaimed_servers()
        if config.bootstrapping:
            if len(unclaimed) < config.ibe_shards:
                raise ConfigError(f"Not enough servers left for client registration committee "
                                  f"(have: {len(unclaimed)}, need: {config.ibe_shards})")
            reg_committee = unclaimed[0:config.ibe_shards]
            unclaimed = unclaimed[config.ibe_shards:]

            for idx, member in enumerate(reg_committee):
                member.role = ClientRegistration(ibe=ibe, index=idx)

        # Step 5. Fill in the gaps with EMIXes
        if not unclaimed:
            raise ConfigError("Not enough servers left to have any EMIXes")
        for server in unclaimed:
            server.role = Emix()

        self.limit_onion_layers(config)

    def limit_onion_layers(self, config: Configuration):
        """Determines the number of onion layers clients are required to wrap messages in.
        If there are not enough servers for the requested number, only use as many as there
        are available servers."""

        emix_count = len([server for server in self.servers if server.is_role(Emix)])

        if emix_count < config.onion_layers:
            print(
                f"WARNING: There were not enough EMIXes for {config.onion_layers} layers of wrapping. "
                f"Falling back to {emix_count} layers based on available EMIXes."
            )

        config.onion_layers = min(config.onion_layers, emix_count)

    def configure_roles(self, config: Configuration, ibe: IBE):
        """Given that roles have been assigned, configure the roles with the appropriate settings."""
        for client in self.clients:
            client.ibe = ibe

        config.prism_common = self.configure_common_params(config, ibe)
        config.server_common = self.configure_servers(config)

        # track client<->dropbox assignments for committee file
        for client in [node for node in self.nodes.values() if node.client_ish]:
            pseudonym = client.pseudonym(config)
            indices = pseudonym.dropbox_indices(config.prism_common["dropbox_count"],
                                                config.prism_common["dropboxes_per_client"])
            dropboxes = [s for s in self.servers_with_role(Dropbox)
                         if s.tags.get("dropbox_index") in indices]
            client.tags["dropboxes"] = dropboxes
            for dropbox in dropboxes:
                db_clients = dropbox.tags.get("db_clients", [])
                db_clients.append(client)
                dropbox.tags["db_clients"] = db_clients

    def configure_common_params(self, config: Configuration, ibe: IBE) -> dict:
        dropbox_roles = [server.role for server in self.servers if isinstance(server.role, Dropbox)]
        dropbox_indices = set(role.index for role in dropbox_roles)

        dropbox_params = Range.dropbox_params(
            len(self.clients),
            len(dropbox_indices) if len(dropbox_indices) else config.server_common.get("vrf_n_ranges", 0),
            config.prism_common["dropboxes_per_client"],
            config.prism_common["dropbox_send_redundancy"],
        )

        prism_config = {
            **config.prism_common,
            **dropbox_params,
            "ibe_shards": ibe.shards,
            "ibe_committee_name": ibe.registrar_name,
            "public_params": ibe.public_params,
            "onion_layers": config.onion_layers,
            "client_emix_count": config.emixes_per_client,
        }

        if config.optimize_salt:
            prism_config["pseudonym_salt"] = optimize_salt(
                [client.name for client in self.clients],
                prism_config["dropbox_count"],
                prism_config["dropboxes_per_client"],
            )

        prism_config["control_traffic"] = config.control_traffic

        return prism_config

    @staticmethod
    def dropbox_params(
        client_count: int,
        dropbox_count: int,
        dropboxes_per_client: int,
        dropbox_send_redundancy: int,
    ) -> dict:
        if not dropboxes_per_client:
            dropboxes_per_client = min(3, min(dropbox_count, math.ceil(dropbox_count / client_count)))

        if not dropbox_send_redundancy:
            dropbox_send_redundancy = math.ceil(dropboxes_per_client / 2)

        return {
            "dropbox_count": dropbox_count,
            "dropboxes_per_client": dropboxes_per_client,
            "dropbox_send_redundancy": dropbox_send_redundancy,
        }

    def configure_servers(self, config: Configuration) -> dict:
        return config.server_common

    def configure_topology(self, config: Configuration):
        """Given node assignments and reachability, determine which connections (direct links, whiteboards, etc)
        are needed between nodes. Fill in Node.linked fields."""
        from prism.config.topology.topology import build_topology

        self.links = build_topology(config.topology, self, config)
        node_links: Dict[str, Set[str]] = {name: set() for name in self.nodes}
        self.graph = build_graph(self.nodes.values(), self.links)

        if config.prism_common.get("ls_routing"):
            diameter = server_diameter(self.nodes.values(), self.links)
            config.server_common["lsp_hops_max"] = diameter

        for link in self.links:
            for member in link.members:
                node_links[member.name].update(set(node.name for node in link.members))

        for name, linked in node_links.items():
            try:
                linked.remove(name)
            except KeyError:
                pass

            self.nodes[name].linked = [
                self.nodes[member]
                for member in linked
                if not (isinstance(self.nodes[name], Client) and isinstance(self.nodes[member], Client))
            ]
