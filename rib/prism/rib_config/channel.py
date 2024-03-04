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
from dataclasses import dataclass, field, fields
from typing import List, Set

from prism.config.environment.link import Link
from prism.common.transport.enums import TransmissionType, ConnectionType
from prism.config.util import snake_case

ALL_TAGS = [
    "ark",  # Should support very large messages (~1KB*arking_server_count)
    "uplink",  # client->emix. Small messages at BAA client messaging rate.
    "downlink",  # dropbox->client. Small messages at BAA client messaging rate.
    "lsp",  # used for LSP backbone
    "mpc",  # used between members of an MPC committee. Should be very fast.
    "epoch",  # used between servers when forming a new epoch, infrequently used
]

CHANNEL_TAGS = {
    "twoSixDirectCpp": ["mpc", "lsp"],
    "twoSixIndirectCpp": ["ark", "uplink", "downlink", "epoch"],

    "obfs": ["mpc", "lsp"],
    "snowflake": ["lsp", "mpc"],

    "destiniAvideo":["ark", "uplink", "downlink", "epoch"],
    "destiniPixelfed": ["ark", "uplink", "downlink", "epoch"],
    "ssEmail": ["ark", "uplink", "downlink", "epoch"],
    "ssRedis": ["ark", "uplink", "downlink", "epoch"],
    "raven": ["ark", "uplink", "downlink", "epoch"],

}


@dataclass
class Channel:
    channel_gid: str
    description: str
    reliable: bool
    is_flushable: bool
    multi_addressable: bool
    send_type: str
    link_direction: str
    max_links: int
    bootstrap: bool
    creator_expected: dict
    loader_expected: dict
    connection_type: ConnectionType
    transmission_type: TransmissionType
    channel_role: str = field(default="CR_BOTH")
    creators_per_loader: int = field(default=1)
    loaders_per_creator: int = field(default=1)
    duration_s: int = field(default=-1)
    period_s: int = field(default=-1)
    mtu: int = field(default=-1)
    bandwidth_bps: int = field(default=500000)
    latency_ms: int = field(default=5000)
    loss: float = field(default=-1.0)
    supported_hints: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)

    @classmethod
    def from_json(cls, json: dict) -> Channel:
        properties = {snake_case(k): v for k, v in json.items()}
        properties["transmission_type"] = TransmissionType[properties["transmission_type"][3:]]
        properties["connection_type"] = ConnectionType[properties["connection_type"][3:]]

        channel_fields = {f.name for f in fields(Channel)}
        properties = {k: v for k, v in properties.items() if k in channel_fields}

        return Channel(**properties, tags=set(CHANNEL_TAGS.get(properties["channel_gid"], set())))

    def score_for_link(self, link: Link) -> int:
        """Returns a score for how compatible the channel is with the requested link.
        0 = Not compatible
        1 = Compatible but not ideal
        2 = Ideal
        """

        if link.connection_type != ConnectionType.UNDEF and link.connection_type != self.connection_type:
            score = 0
        elif link.has_clients() and self.connection_type == ConnectionType.DIRECT:
            score = 0
        elif link.tags.intersection(self.tags):
            score = 2
        else:
            score = 1

        return score

    @classmethod
    def missing_tags(cls, channels: List[Channel]):
        """
        Returns a list of tags that the selected channels do not cover.
        """
        missing_tags = set(ALL_TAGS.copy())

        for channel in channels:
            missing_tags.difference_update(channel.tags)

        return missing_tags
