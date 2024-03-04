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
from dataclasses import dataclass, field
from typing import List, Optional

from prism.common.crypto.halfkey import PublicKey
from prism.common.message import LinkAddress, HalfKeyMap
from prism.common.transport.enums import LinkType


@dataclass
class LinkProfile:
    address: LinkAddress
    description: str
    personas: List[str]
    role: str
    link_type: LinkType
    loaded: bool = field(default=False)

    @classmethod
    def from_dict(cls, channel_id: Optional[str], d: dict) -> LinkProfile:
        if "channel_id" in d:
            channel_id = d["channel_id"]
            del d["channel_id"]
        d["address"] = LinkAddress(channel_id, d["address"])
        description = d["description"].lower()
        if "send" in description:
            d["link_type"] = LinkType.SEND
        elif "receive" in description or "recv" in description:
            d["link_type"] = LinkType.RECV
        elif "bidi" in description:
            d["link_type"] = LinkType.BIDI
        else:
            d["link_type"] = LinkType.UNDEF

        return LinkProfile(**d)

    def to_dict(self):
        return {
            "address": self.address.link_address,
            "channel_id": self.address.channel_id,
            "description": self.description,
            "personas": self.personas,
            "role": self.role,
        }

    def __repr__(self):
        return f"LinkProfile({self.address.channel_id}, {self.role}, {self.link_type}, {self.personas})"


@dataclass
class NeighborInfo:
    name: str
    pseudonym: bytes
    tag: str
    public_key: Optional[PublicKey] = field(default=None)
    control_addresses: List[LinkAddress] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> NeighborInfo:
        pseudonym = bytes.fromhex(d["pseudonym"])
        if "public_key" in d:
            public_key = HalfKeyMap.decode(bytes.fromhex(d["public_key"])).to_key()
        else:
            public_key = None

        return NeighborInfo(
            name=d["name"],
            pseudonym=pseudonym,
            tag=d["tag"],
            public_key=public_key,
        )


@dataclass
class GenesisInfo:
    neighbors: List[NeighborInfo]
    send_links: List[LinkProfile]
    broadcast_links: List[LinkProfile]
    receive_links: List[LinkProfile]

    def __repr__(self):
        s = "Genesis Info:\n"
        if self.send_links:
            s += "Send links:\n"
            for link in self.send_links:
                s += f"  {link}\n"
        if self.receive_links:
            s += "Receive links:\n"
            for link in self.receive_links:
                s += f"  {link}\n"
        if self.broadcast_links:
            s += "Broadcast links:\n"
            for link in self.broadcast_links:
                s += f"  {link}\n"
        return s

    @property
    def loaded(self):
        return all(
            profile.loaded for profile in
            itertools.chain(self.send_links, self.broadcast_links, self.receive_links)
        )

    @property
    def unloaded_send_links(self) -> List[LinkProfile]:
        return [profile for profile in self.send_links if not profile.loaded]

    @property
    def unloaded_receive_links(self) -> List[LinkProfile]:
        return [profile for profile in self.receive_links if not profile.loaded]

    @property
    def unloaded_broadcast_links(self) -> List[LinkProfile]:
        return [profile for profile in self.broadcast_links if not profile.loaded]
