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
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Iterable

import networkx as nx
from networkx.algorithms import diameter

from prism.config.environment.link import Link
from prism.config.node import Node, Server, Client
from prism.config.node.server import Dropbox, Dummy


def graph_node(node: Node) -> Tuple[str, Dict[str, str]]:
    if isinstance(node, Server):
        if node.is_role(Dropbox):
            if node.tags.get("mpc_leader"):
                color = "cadetblue"
            else:
                color = "cadetblue1"
        else:
            color = "chartreuse"
    else:
        color = "gold"

    return node.name, {"color": color}


def build_graph(nodes: Iterable[Node], links: Iterable[Link]) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(graph_node(n) for n in nodes if not isinstance(n, Server) or not n.is_role(Dummy))

    for link in links:
        for sender in link.senders:
            for receiver in link.receivers:
                if sender == receiver or sender.name not in g or receiver.name not in g:
                    continue
                if isinstance(sender, Server):
                    if sender.is_role(Dropbox) and isinstance(receiver, Client):
                        continue

                g.add_edge(sender.name, receiver.name)

    return g


def server_diameter(nodes: Iterable[Node], links: Iterable[Link]) -> int:
    # FIXME - make sure to revisit this once MPC peers can be servers
    servers = [node for node in nodes
               if isinstance(node, Server)
               and not node.tags.get("mpc_party_id")
               and not node.client_ish]
    g = build_graph(servers, links)
    return diameter(g)


def can_draw(test_range) -> bool:
    if len(test_range.nodes) > 200:
        return False

    from importlib.util import find_spec
    from shutil import which

    required_modules = ["pydot"]
    required_commands = ["dot"]

    for m in required_modules:
        if not find_spec(m):
            return False

    for c in required_commands:
        if not which(c):
            return False

    return True


def draw_graph(g: nx.Graph, out: Path):
    from networkx.drawing.nx_pydot import write_dot

    dot_path = out.with_suffix(".dot")
    write_dot(g, dot_path)
    image_format = out.suffix[1:]
    subprocess.run(["dot", f"-T{image_format}", dot_path, "-o", out])
