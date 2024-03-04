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
import itertools
import math
from random import Random
from collections import defaultdict
from typing import List, Iterable, Optional

from prism.common.transport.enums import ConnectionType
from prism.config.config import Configuration
from prism.config.environment import Range
from prism.config.environment.link import Link
from prism.config.error import ConfigError
from prism.config.node import Node
from prism.config.node.server import Emix, Dropbox
from prism.config.topology.util import connect_clients_to_emixes, connect_clients_to_dropboxes


class NodeUsage:
    """
    Helper class for tracking how many times a node has been used in making a set of connections,
    to try to minimize fan-out on any given node.

    Also handles building a list of links to return.
    """
    def __init__(self, connection_type, tags: Optional[Iterable[str]]):
        self.connection_type = connection_type
        self.tags = tags
        self.links = []
        self.linked_pairs = set()
        self.node_usage = defaultdict(lambda: 0)

    def add_link(self, n1, n2):
        if n1 == n2:
            import traceback
            raise ConfigError("Trying to link a node to itself..." + "\n".join(traceback.format_tb(None)))
        if self.linked(n1, n2):
            return

        members = frozenset([n1, n2])
        self.links.append(Link(members=members, connection_type=self.connection_type, tags=self.tags))
        self.linked_pairs.add(members)
        self.node_usage[n1] += 1
        self.node_usage[n2] += 1

    def linked(self, n1, n2) -> bool:
        return frozenset([n1, n2]) in self.linked_pairs

    def __getitem__(self, item):
        return self.node_usage[item]

    def minimal_nodes(self, nodes: List[Node]) -> List[Node]:
        min_usage = min(self.node_usage[n] for n in nodes)
        return [node for node in nodes if self.node_usage[node] == min_usage]


def decide_cluster_count(emix_count: int) -> int:
    emixes_per_cluster = math.ceil(math.sqrt(emix_count))
    return math.ceil(emix_count / emixes_per_cluster)


def cluster_emixes(emixes: List[Node], cluster_count: int) -> List[List[Node]]:
    cluster_size = math.floor(len(emixes) / cluster_count)

    # The first batch of clusters will have to take on an additional node
    bonus_clusters = len(emixes) % cluster_count
    clusters = []

    next_cluster = 0
    for i in range(cluster_count):
        size = cluster_size
        if i < bonus_clusters:
            size += 1

        clusters.append(emixes[next_cluster:next_cluster+size])
        next_cluster += size

    return clusters


def cluster_internal_full(cluster: List[Node], ctype: ConnectionType) -> List[Link]:
    """
    A fully connected internal cluster topology.
    """
    return [Link(members=cluster, connection_type=ctype, tags=["lsp"])]


def cluster_internal_skip_ring(cluster: List[Node], ctype: ConnectionType) -> List[Link]:
    """
    An internal cluster topology that tries to minimize both diameter and fan-out by arranging the nodes in a ring, then
    adding links to each node to nodes approximately 1/3rd ahead and behind on the ring.
    """
    node_usage = NodeUsage(ctype, tags=["lsp"])
    skip_distance = math.ceil(len(cluster) / 3)

    for i, node in enumerate(cluster):
        next_node = cluster[(i + 1) % len(cluster)]
        skip_node = cluster[(i + skip_distance) % len(cluster)]

        if node != next_node:
            node_usage.add_link(node, next_node)
        if node != skip_node:
            node_usage.add_link(node, skip_node)

    return node_usage.links


def inter_cluster_links(clusters: List[List[Node]], ctype: ConnectionType) -> List[Link]:
    """
    Creates links between clusters, ensuring that each cluster has a link to each other cluster, while minimizing
    the number of inter-cluster links that any individual node has.

    TODO - Support more than one link per cluster pair
    TODO - If more than one link between clusters, try to minimize overall route distances
    """
    node_usage = NodeUsage(ctype, tags=["lsp"])

    for source_index, source_cluster in enumerate(clusters):
        for target_cluster in clusters[source_index+1:]:
            source_node = node_usage.minimal_nodes(source_cluster)[0]
            target_node = node_usage.minimal_nodes(target_cluster)[0]
            node_usage.add_link(source_node, target_node)

    return node_usage.links


def clustered(test_range: Range, config: Configuration) -> List[Link]:
    """
    The clustered topology divides EMIXes into a number of densely connected clusters,
    with sparse links between clusters. Each dropbox is connected to multiple members of one cluster,
    and each client is connected to a random selection of EMIXes.
    """
    def connection_type(indirect: bool) -> ConnectionType:
        if indirect:
            return ConnectionType.INDIRECT
        else:
            return ConnectionType.DIRECT

    rand = Random(config.random_seed)
    links = []
    emixes = test_range.servers_with_role(Emix)
    cluster_count = config.emix_clusters or decide_cluster_count(len(emixes))
    clusters = cluster_emixes(emixes, cluster_count)

    # Build links within clusters
    for cluster in clusters:
        # links.extend(cluster_internal_full(cluster, connection_type(config.indirect_emix_to_emix)))
        links.extend(cluster_internal_skip_ring(cluster, connection_type(config.indirect_emix_to_emix)))

    # Build links between clusters
    links.extend(inter_cluster_links(clusters, connection_type(config.indirect_cluster_to_cluster)))

    dropbox_leaders = [
        server for server in test_range.servers_with_role(Dropbox)
        if server.tags.get("dropbox_index") is not None
    ]
    for dropbox, cluster in zip(dropbox_leaders, itertools.cycle(clusters)):
        # Build links inside Dropbox committees
        committee = dropbox.tags.get("mpc_committee_members")
        if committee:
            links.append(Link(members=committee, connection_type=ConnectionType.DIRECT, tags=["mpc"]))

        # Build links between dropboxes and clusters
        for emix in rand.sample(cluster, min(config.emixes_per_dropbox, len(cluster))):
            links.append(
                Link(
                    members=[emix, dropbox],
                    connection_type=connection_type(config.indirect_emix_to_dropbox),
                    tags=["lsp"],
                )
            )

    # Build links between clients and emixes
    links.extend(connect_clients_to_emixes(config, test_range, rand))

    if config.genesis_downlinks:
        links.extend(connect_clients_to_dropboxes(test_range))

    return links
