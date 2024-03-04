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
import random
from typing import List

from prism.config.config import Configuration
from prism.config.environment import Range
from prism.config.environment.link import Link
from prism.config.error import ConfigError
from prism.config.node.server import Emix
from prism.config.topology.util import connect_clients_to_emixes
from prism.common.transport.enums import ConnectionType


def ring_topology(test_range: Range, config: Configuration) -> List[Link]:
    """All EMIXes get connected in ring topology. No other links exist."""
    links = []

    # Step 1: Create ring among sorted EMIX nodes
    emix_nodes = set(test_range.servers_with_role(Emix))
    if len(emix_nodes) == 0:
        raise ConfigError("Need at least 1 EMIX for ring topology")
    emix_array = list(sorted(emix_nodes))  # ordered list of EMIXes
    for i, x in enumerate(emix_array[:-1]):
        links.extend([
            Link(members={x, emix_array[i+1]},
                 connection_type=ConnectionType.DIRECT,
                 tags={"lsp", x.name}),
        ])
    links.extend([Link(members={emix_array[-1], emix_array[0]},
                       connection_type=ConnectionType.DIRECT,
                       tags={"lsp", emix_array[-1].name}),
                  ])

    # Step 2: Build links between clients and emixes
    rand = random.Random(config.random_seed)
    links.extend(connect_clients_to_emixes(config, test_range, rand))

    return links
