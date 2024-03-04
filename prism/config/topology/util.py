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
from collections import defaultdict
from random import Random
from typing import List

from prism.common.transport.enums import ConnectionType
from prism.config.config import Configuration
from prism.config.environment import Range
from prism.config.environment.link import Link
from prism.config.node.server import ClientRegistration, Emix, Dropbox


def connect_clients_to_emixes(config: Configuration, test_range: Range, rand: Random) -> List[Link]:
    registration_committee = set(test_range.servers_with_role(ClientRegistration))
    clients = set(test_range.clients).union(registration_committee)
    emixes = set(test_range.servers_with_role(Emix))
    emix_clients = defaultdict(list)
    links = []

    for client in clients:
        for emix in rand.sample(emixes, min(config.emixes_per_client, len(emixes))):
            if config.genesis_uplinks:
                links.append(Link(
                    senders=[client],
                    receivers=[emix],
                    connection_type=ConnectionType.INDIRECT,
                    tags=["uplink"]
                ))
            emix_clients[emix].append(client)

    for emix, clients in emix_clients.items():
        links.append(Link(senders=[emix], receivers=clients, connection_type=ConnectionType.INDIRECT, tags=["ark"]))

    return links


def connect_clients_to_dropboxes(test_range: Range) -> List[Link]:
    links = []
    dropbox_leaders = [
        server for server in test_range.servers_with_role(Dropbox)
        if server.tags.get("dropbox_index") is not None
    ]

    for dropbox in dropbox_leaders:
        if not dropbox.tags.get("db_clients"):
            continue

        links.append(Link(senders=[dropbox],
                          receivers=dropbox.tags.get("db_clients", []),
                          connection_type=ConnectionType.INDIRECT,
                          tags=["downlink"]))

    return links
