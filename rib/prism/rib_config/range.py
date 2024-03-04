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

import re
from typing import Optional

from prism.config.environment.range import Range
from prism.config.error import ConfigError
from prism.config.node import Node, Client, Server

ENCLAVE_REGEX = re.compile(r"([A-Za-z]+\d+).*")


class RIBRange(Range):
    def __init__(self, range_config: dict):
        super().__init__({node.name: node for node in map(from_race_node, range_config["range"]["RACE_nodes"])})
        self.range_config = range_config
        # self.configure_reachability()

    def configure_reachability(self):
        for node in self.nodes.values():
            if isinstance(node, Client):
                node.reachable = self.servers
            else:
                node.reachable = [other for other in self.nodes.values() if node is not other]


def parse_enclave(race_node: dict) -> Optional[str]:
    enclave = race_node.get("enclave", "global")
    if enclave == "global":
        return enclave

    enclave_match = ENCLAVE_REGEX.match(enclave)
    if enclave_match:
        return enclave_match.group(1)
    else:
        return None


def from_race_node(race_node: dict) -> Node:
    name = race_node["name"]
    nat = race_node.get("nat", False)
    enclave = parse_enclave(race_node)

    if "client" in name:
        node = Client(name, nat=nat, enclave=enclave)
    elif "server" in name:
        node = Server(name, nat=nat, enclave=enclave)
    else:
        raise ConfigError("Node {name} has unknown type.")

    return node
