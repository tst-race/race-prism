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
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple, Set

from prism.client.server_db import ServerDB, ServerRecord
from prism.common.message import PrismMessage
from prism.common.message_utils import emix_forward
from prism.common.transport.epoch_transport import EpochTransport


@dataclass
class MessageRoute:
    route: List[ServerRecord]
    channel: str
    target: ServerRecord
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __str__(self):
        return " -> ".join(s.name for s in [*self.route, self.target])

    def wrap(self, message: PrismMessage):
        target = self.target
        for emix in reversed(self.route):
            message = emix_forward(emix, target, message)
            target = emix
        return message

    def is_dead(self, server_db: ServerDB) -> bool:
        return any(not server_db.can_reach(s) for s in [*self.route, self.target])

    @property
    def head(self):
        return self.route[0]

    @property
    def tail(self):
        return [*self.route[1:], self.target]


def server_channels(transport: EpochTransport, servers: List[ServerRecord]) -> Set[str]:
    live_channels = {channel.channel_id for channel in transport.channels if channel.status.usable}
    channels = {address.channel_id
                for server in servers
                for address in server.ark.link_addresses}
    return channels.intersection(live_channels)


def find_start(
        server_db: ServerDB,
        transport: EpochTransport,
        routes_used: List[MessageRoute],
) -> Tuple[List[ServerRecord], Set[str]]:
    candidate_pool = [server for server in server_db.reachable_emixes
                      if server.ark.link_addresses]

    if not routes_used:
        return candidate_pool, server_channels(transport, candidate_pool)

    starts_used = {route.head.pseudonym for route in routes_used}

    if not candidate_pool:
        return [], set()

    channels_used = {route.channel for route in routes_used}

    def has_novel_channel(server: ServerRecord):
        return server_channels(transport, [server]) - channels_used

    channel_candidates = [server for server in candidate_pool if has_novel_channel(server)]

    if not channel_candidates:
        channel_candidates = candidate_pool

    candidates = [server for server in channel_candidates if server.pseudonym not in starts_used]

    if not candidates:
        candidates = channel_candidates

    channels_unused = server_channels(transport, candidates)

    if channels_unused.issubset(channels_used):
        channels_unused = channels_used
    else:
        channels_unused = channels_unused - channels_used

    return candidates, channels_unused


def find_route(
        server_db: ServerDB,
        transport: EpochTransport,
        target: ServerRecord,
        layers: int,
        routes_used: List[MessageRoute]
) -> Optional[MessageRoute]:
    if not server_db.can_reach(target):
        return None

    routes = []

    # Filter the list of starting EMIXes to ones that haven't NARKed the target dropbox
    # and support at least one live channel
    starts, channels = find_start(server_db, transport, routes_used)

    # For each starting point, tack on some valid EMIXes that haven't been NARKed
    for start in starts:
        potential_hops = [emix for emix in server_db.reachable_emixes if emix != start]

        if len(potential_hops) + 1 < layers:
            continue

        routes.append([start, *random.sample(potential_hops, layers - 1)])

    if not routes:
        return None

    route = random.choice(routes)
    channel = random.choice([address.channel_id
                             for address in route[0].ark.link_addresses
                             if address.channel_id in channels])

    return MessageRoute(route, channel, target)
