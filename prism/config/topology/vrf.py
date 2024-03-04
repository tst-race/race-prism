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
import random
from statistics import mean
from typing import List

import networkx as nx

from prism.common.transport.enums import ConnectionType
from prism.common.vrf.octets import i2bytes
from prism.common.vrf.distribution import VRFDistribution
from prism.common.vrf.sortition import VRFSortition
from prism.config.config import Configuration
from prism.config.environment import Range
from prism.config.environment.link import Link
from prism.config.error import ConfigError
from prism.config.node.server import Emix, Dropbox, Dummy
from prism.config.topology.util import connect_clients_to_emixes, connect_clients_to_dropboxes


def calc_p_from(c: float, n: int) -> float:
    assert n > 0
    # use slightly adjusted (namely by factor c) formula for giant component emerging in ER:
    return min(c * math.log(n) / n, 1)  # make sure to never return anything > 1


def randomized(test_range: Range, config: Configuration) -> List[Link]:
    """
    The randomized topology works on the direct, unicast, bidirectional links between servers.
    It then assigns the indirect links for clients similar to "clustered" and other topologies.

    First, all MPC committees get fully connected (for the first 3-4 members only).  Then, all
    EMIXes and DROPBOX leaders get connected in a number of ways (depending on the current config):
    In the following, c is a small factor of 2, 3, 4,... to improve connectivity.
    - if vrf_b = 0, then use Erdos-Renyi (ER) random graph between all nodes with p=c*ln(n)/n probability
    - if vrf_b > 0 (typically 1, 2, or 3) then connect each DROPBOX leader to this number of EMIXes chosen
      at random; the EMIXes themselves get ordered into a simple ring lattice (k=2) and then shortcuts for
      each EMIX_i with i = 1..n to the higher-order EMIXes with which EMIX_i is not yet connected, using
      probability p_i=c*ln(n)/(n*i)
    """
    links = []
    config_error = ""

    emix_nodes = set(test_range.servers_with_role(Emix))
    assert len(emix_nodes) >= 1
    emix_array = list(sorted(emix_nodes))  # ordered list of EMIXes
    # distribute probabilities of EMIX subsets of size <b> (or #EMIXes, if smaller) uniformly:
    emix_combos = list(itertools.combinations(emix_nodes, min(len(emix_array),
                                                              config.server_common["vrf_b_db_emix"])))
    emix_combo_sortition = VRFSortition(VRFDistribution.choice_distribution(list(range(len(emix_combos)))))
    print(f" ~~~ VRF Step 5: #EMIX = {len(emix_array)} yields #combos = {len(emix_combos)} " +
          f"(of length = {config.server_common['vrf_b_db_emix']})")

    db_leader_nodes = set([s for s in test_range.servers_with_role(Dropbox) if s.tags.get("dropbox_index") is not None])

    # Step 1: Fully connect DROPBOX committees
    for dropbox in db_leader_nodes:
        # Build links inside Dropbox committees
        committee = dropbox.tags.get("mpc_committee_members")
        if committee:
            links.append(Link(members=committee, connection_type=ConnectionType.DIRECT, tags=["mpc"]))

    # Step 2: LSP topology: EMIXes and DROPBOX leaders with DIRECT connections;
    #         use second round VRF for topology (either ER or more structured):
    graph = nx.Graph()
    if config.server_common["vrf_b_db_emix"] == 0:
        # use Erdos-Renyi (ER)
        node_array = list(sorted(emix_nodes | db_leader_nodes))
        p = calc_p_from(config.server_common["vrf_c_p_factor"], len(node_array))
        assert 0 <= p <= 1
        sortition = VRFSortition(VRFDistribution.binary_distribution(p))

        for attempt in range(config.vrf_config_attempts):
            config_error = f"ER topology (attempt #{attempt + 1} of {config.vrf_config_attempts}) not connected!"
            graph = nx.Graph()
            graph.add_nodes_from(node_array)
            for i, x in enumerate(node_array):
                for y in node_array[i + 1:]:
                    assert x < y
                    # perform Link Sortition for link between server x and y
                    alpha = i2bytes(random.randint(0, 2 ** 256 - 1), 2048)
                    result, proof = sortition.sort_and_prove(x.tags.get("vrf_key"), alpha)
                    if eval(result):
                        # undirected graph, so only need one edge from x < y
                        graph.add_edge(x, y, proof=proof, p=p)
            if nx.algorithms.is_connected(graph):
                config_error = ""
                break
    elif config.server_common["vrf_b_db_emix"] > 0:
        # more structured and guaranteed to be connected topology:
        # 1) create EMIX ring
        graph.add_nodes_from(emix_array)
        one_sortition = VRFSortition(VRFDistribution.binary_distribution(1))
        for i, x in enumerate(emix_array[:-1]):
            # perform Link Sortition (but with p=1) for link between server x and next neighbor in ring:
            alpha = i2bytes(random.randint(0, 2 ** 256 - 1), 2048)
            result, proof = one_sortition.sort_and_prove(x.tags.get("vrf_key"), alpha)
            assert eval(result)  # should always be True
            graph.add_edge(x, emix_array[i+1], proof=proof, p=1)
        # perform Link Sortition (but with p=1) for link to close the ring:
        alpha = i2bytes(random.randint(0, 2 ** 256 - 1), 2048)
        result, proof = one_sortition.sort_and_prove(emix_array[-1].tags.get("vrf_key"), alpha)
        assert eval(result)  # should always be True
        graph.add_edge(emix_array[-1], emix_array[0], proof=proof, p=1)  # closing the loop
        # 2) random shortcuts with decreasing likelihood:
        for i, x in enumerate(emix_array):
            p_i = calc_p_from(config.server_common["vrf_c_p_factor"], len(emix_array))/(i + 1)
            if p_i == 0.0:
                continue
            sortition = VRFSortition(VRFDistribution.binary_distribution(p_i))
            for j, y in enumerate(emix_array[i+1:]):
                if i == 0 and j == len(emix_array) - 1:
                    continue  # skip shortcut for first->last EMIX as they are already connected via ring
                assert x < y
                # perform Link Sortition for link between server x and y
                alpha = i2bytes(random.randint(0, 2 ** 256 - 1), 2048)
                result, proof = sortition.sort_and_prove(x.tags.get("vrf_key"), alpha)
                if eval(result):
                    # undirected graph, so only need one edge from x < y
                    graph.add_edge(x, y, proof=proof, p_i=p_i)
        # 3) connect each DROPBOX to a few random EMIXes
        graph.add_nodes_from(db_leader_nodes)
        for db in db_leader_nodes:
            alpha = i2bytes(random.randint(0, 2 ** 256 - 1), 2048)
            emix_combo_index_str, proof = emix_combo_sortition.sort_and_prove(db.tags.get("vrf_key"), alpha)
            assert int(emix_combo_index_str) in range(len(emix_combos))
            for emix in emix_combos[int(emix_combo_index_str)]:
                assert emix in emix_nodes
                graph.add_edge(db, emix, proof=proof)
    else:
        config_error = f"Assuming that b={config.server_common['vrf_b_db_emix']} is >= 0 for VRF Topology"

    # Step 3: connect DUMMY servers to randomly chosen EMIXes:
    dummy_nodes = set(test_range.servers_with_role(Dummy))
    graph.add_nodes_from(dummy_nodes)
    for dummy in dummy_nodes:
        alpha = i2bytes(random.randint(0, 2 ** 256 - 1), 2048)
        emix_combo_index_str, proof = emix_combo_sortition.sort_and_prove(dummy.tags.get("vrf_key"), alpha)
        assert int(emix_combo_index_str) in range(len(emix_combos))
        for emix in emix_combos[int(emix_combo_index_str)]:
            assert emix in emix_nodes
            graph.add_edge(dummy, emix, proof=proof)

    if config_error:
        raise ConfigError(config_error)

    for x, y, proof in graph.edges.data("proof"):
        links.extend([
            Link(members={x, y},
                 connection_type=ConnectionType.DIRECT,
                 tags={"lsp", x.name, proof}),
        ])
    print(f" ~~~ VRF Step 6: Topology with {len(graph)} EMIX and DB leaders and DUMMY " +
          f"(vrf_c_p_factor={config.server_common['vrf_c_p_factor']:.2f}), " +
          f"avg. degree={mean([deg for _, deg in graph.degree()])}, " +
          f"max degree={max([deg for _, deg in graph.degree()])}, " +
          f"diameter={nx.algorithms.diameter(graph)}")

    # Step 4: Build links between clients and emixes
    rand = random.Random(config.random_seed)
    links.extend(connect_clients_to_emixes(config, test_range, rand))

    if config.genesis_downlinks:
        links.extend(connect_clients_to_dropboxes(test_range))

    return links
