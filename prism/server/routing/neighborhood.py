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
from datetime import datetime, timedelta
from typing import Dict, List, Union, Optional, Tuple

from jaeger_client import SpanContext

from prism.common.config import configuration
from prism.common.crypto.halfkey import PublicKey
from prism.common.epoch.genesis import LinkProfile
from prism.common.logging import get_logger
from prism.common.message import PrismMessage, LinkAddress, HalfKeyMap
from prism.common.transport.transport import Link


DATE_MIN = datetime.utcfromtimestamp(0)


class Neighbor:
    def __init__(self, name: str, pseudonym: bytes, public_key: PublicKey, control_addresses: List[LinkAddress], tag: str):
        self.name = name
        self.pseudonym = pseudonym
        self.public_key = public_key
        self.control_addresses = control_addresses
        self.tag = tag
        self.ls_db_size = 0

        # Outbound links
        self.data_links: List[Link] = []

        # The last time a message was received from this neighbor
        self.last_received = DATE_MIN
        # The last time we tried to initiate a new connection with this neighbor
        self.last_initiated = DATE_MIN
        # The last time we tried to request a copy of this neighbor's LS DB
        self.last_requested_db = DATE_MIN

    def __str__(self):
        if self.online:
            status = 'online'
        elif self.dead:
            status = 'dead'
        else:
            status = 'offline'

        return f"{self.name} ({self.pseudonym.hex()[:6]}): " \
               f"{status}, {len(self.data_links)} links ({self.tag}), " \
               f"{'has key' if self.public_key else 'no key'}, " \
               f"db_size {self.ls_db_size}"

    async def send(self, message: PrismMessage, context: SpanContext) -> bool:
        sent = False
        for link in self.data_links:
            if not link.can_send:
                continue
            if await link.send(message, context):
                sent = True

        return sent

    def save_data(self):
        return {
            "name": self.name,
            "pseudonym": self.pseudonym.hex(),
            "public_key": HalfKeyMap.from_key(self.public_key).encode().hex(),
            "control_addresses": [address.encode().hex() for address in self.control_addresses],
            "data_links": [link.profile.to_dict() for link in self.data_links],
            "tag": self.tag,
        }

    @classmethod
    def from_save_data(cls, data: dict):
        return Neighbor(
            name=data["name"],
            pseudonym=bytes.fromhex(data["pseudonym"]),
            public_key=HalfKeyMap.decode(bytes.fromhex(data["public_key"])).to_key(),
            control_addresses=[LinkAddress.decode(bytes.fromhex(a)) for a in data["control_addresses"]],
            tag=data["tag"],
        )

    @property
    def dead(self):
        if self.online:
            return False

        if self.last_received == DATE_MIN:
            return False

        dead_timeout = timedelta(milliseconds=configuration.ls_hello_timeout_ms *
                                              configuration.ls_alive_factor *
                                              configuration.ls_dead_factor)
        if datetime.utcnow() - self.last_received < dead_timeout:
            return False

    @property
    def online(self):
        if not any(link for link in self.data_links if link.can_send):
            return False

        timeout = timedelta(milliseconds=configuration.ls_hello_timeout_ms * configuration.ls_alive_factor)
        return datetime.utcnow() - self.last_received < timeout


class Neighborhood:
    neighbors: Dict[bytes, Neighbor]

    def __init__(self, epoch: str):
        self.neighbors = {}
        self.epoch = epoch
        self.logger = get_logger(__name__, epoch=epoch)

    def __getitem__(self, item: Union[str, bytes]) -> Optional[Neighbor]:
        if isinstance(item, bytes):
            return self.neighbors.get(item)
        elif isinstance(item, str):
            for neighbor in self.neighbors.values():
                if neighbor.name == item:
                    return neighbor
        return None

    def __contains__(self, item) -> bool:
        return bool(self.__getitem__(item))

    def __iter__(self):
        yield from self.neighbors.values()

    @property
    def dead_neighbors(self):
        return {neighbor for neighbor in self.neighbors.values() if neighbor.dead}

    def update(self, name: str, pseudonym: bytes, public_key: PublicKey, addresses: List[LinkAddress], tag: str):
        existing = self.neighbors.get(pseudonym)
        if not existing:
            self.neighbors[pseudonym] = Neighbor(name, pseudonym, public_key, addresses, tag)
        else:
            existing.control_addresses = addresses
            existing.tag = tag

    def debug_dump(self, logger):
        logger.debug(f"Neighbor report ({self.epoch}):")
        for neighbor in self:
            logger.debug(str(neighbor))
        logger.debug("\n")

    def save_data(self) -> dict:
        return {
            "neighbors": [neighbor.save_data() for neighbor in self]
        }

    def load_data(self, data: dict) -> List[Tuple[bytes, LinkProfile]]:
        profiles = []
        for n_data in data["neighbors"]:
            neighbor = Neighbor.from_save_data(n_data)
            self.neighbors[neighbor.pseudonym] = neighbor

            for profile_dict in n_data.get("data_links"):
                profile = LinkProfile.from_dict(None, profile_dict)
                profiles.append((neighbor.pseudonym, profile))

        return profiles
