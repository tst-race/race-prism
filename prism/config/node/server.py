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

import math
import os
import time
from dataclasses import dataclass, field
from typing import List

from prism.common.crypto.halfkey.ecdh import EllipticCurveDiffieHellman
from prism.common.pseudonym import Pseudonym
from prism.config.config import Configuration
from prism.config.ibe import IBE
from prism.config.node.node import Node


@dataclass(eq=True, unsafe_hash=True)
class Server(Node):
    role: ServerRole = field(default=None, compare=False)

    def __post_init__(self):
        self.private_key = EllipticCurveDiffieHellman().generate_private()
        self._ark_key = None

    @property
    def ark_key(self):
        if self._ark_key is None:
            from prism.common.message import HalfKeyMap
            # noinspection PyAttributeOutsideInit
            self._ark_key = HalfKeyMap.from_key(self.private_key.public_key())

        return self._ark_key

    def unclaimed(self):
        return "claimed" not in self.tags

    def claim(self):
        self.tags["claimed"] = True

    def is_role(self, role: type) -> bool:
        return isinstance(self.role, role)

    def config(self, config: Configuration) -> dict:
        persona = {
            **super().config(config),
            "name": self.name,
            "pseudonym": self.pseudonym(config).pseudonym.hex(),
            "role": self.role.role_name,
        }
        persona.update(self.role.config(config))

        if config.preload_arks:
            persona["key_data"] = self.private_key.serialize().hex()

        return persona

    def pseudonym(self, config: Configuration) -> Pseudonym:
        primary_role = self.role

        if isinstance(primary_role, ClientRegistration):
            return Pseudonym.from_address(primary_role.name, config.prism_common["pseudonym_salt"])
        else:
            return Pseudonym.from_address(self.name, config.server_pseudonym_salt)

    def ark(self, config: Configuration):
        from prism.common.message import PrismMessage, TypeEnum, HalfKeyMap

        primary_role = self.role
        ark_data = primary_role.ark_data(config)
        if not ark_data:
            return None

        return PrismMessage(
            msg_type=TypeEnum.ANNOUNCE_ROLE_KEY,
            certificate=b'',
            nonce=os.urandom(12),
            half_key=HalfKeyMap.from_key(self.private_key.public_key()),
            name=self.name,
            pseudonym=self.pseudonym(config).pseudonym,
            expiration=int(time.time()) + (100 * 365 * 24 * 60 * 60),
            **primary_role.ark_data(config),
        )

    def lsp_cost(self):
        return self.role.lsp_cost()

    def lsp(self, config: Configuration):
        from prism.common.message import PrismMessage, TypeEnum, NeighborInfoMap

        lsp_neighbors = [node for node in self.linked
                         if isinstance(node, Server) and not node.is_role(ClientRegistration)]

        return PrismMessage(
            msg_type=TypeEnum.LSP,
            name=self.name,
            originator=self.pseudonym(config).pseudonym,
            micro_timestamp=int(time.time() * 1e6),
            ttl=100 * 365 * 24 * 60 * 60,  # TTL: 100 years
            neighbors=[NeighborInfoMap(pseudonym=n.pseudonym(config).pseudonym, cost=self.lsp_cost())
                       for n in lsp_neighbors],
            # sub_msg=self.ark(config),
            hop_count=0,
            sender=self.pseudonym(config).pseudonym,
        )


class ServerRole:
    role_name: str = None

    def ark_data(self, config: Configuration) -> dict:
        return {
            "role": self.role_name,
        }

    def lsp_cost(self) -> int:
        return 1

    def config(self, config: Configuration) -> dict:
        return {}


class Dropbox(ServerRole):
    index: int
    role_name = "DROPBOX"

    def __init__(self, index: int):
        super().__init__()
        self.index = index

    def ark_data(self, config: Configuration) -> dict:
        return {
            **super().ark_data(config),
            "dropbox_index": self.index,
        }

    def lsp_cost(self) -> int:
        return 100

    def config(self, config: Configuration) -> dict:
        return {"db_index": self.index}


class MPCDropbox(Dropbox):
    party_id: int
    committee: List[Server]
    role_name = "DROPBOX_LF"

    def __init__(self, index: int, party_id: int, committee: List[Server]):
        super().__init__(index)
        self.party_id = party_id
        self.committee = committee

    def ark_data(self, config: Configuration) -> dict:
        from prism.common.crypto.secretsharing import get_ssobj
        if self.party_id:
            return {}

        nparties = len(self.committee)
        threshold = config.prism_common.get("threshold", math.ceil(nparties / 2))
        modulus = int(config.prism_common.get("mpc_modulus"))
        sharing = get_ssobj(nparties, threshold, modulus)

        return {
            **super().ark_data(config),
            "secret_sharing": sharing.parameters,
            "worker_keys": [peer.ark_key for peer in self.committee],
        }

    def config(self, config: Configuration) -> dict:
        return {
            **super().config(config),
            "party_id": self.party_id,
            "committee_members": ",".join(node.name for node in self.committee),
            "committee_pseudonyms": ",".join(node.pseudonym(config).hex() for node in self.committee),
        }


class Emix(ServerRole):
    role_name = "EMIX"


class Dummy(ServerRole):
    role_name = "DUMMY"

    def ark_data(self, config: Configuration) -> dict:
        return {}


class ClientRegistration(ServerRole):
    role_name = "CLIENT_REGISTRATION"
    client_registration_index: int

    def __init__(self, ibe: IBE, index: int):
        super().__init__()
        self.ibe = ibe
        self.ibe_secret = ibe.ibe_secrets[index]
        self.public_param_shard = ibe.public_param_shards[index]
        self.public_params = ibe.public_params
        self.client_registration_index = index
        self.name = f"{ibe.registrar_name}-{self.client_registration_index+1}"

    def ark_data(self, config: Configuration) -> dict:
        return {}

    def config(self, config: Configuration) -> dict:
        return {
            **super().config(config),
            **self.ibe.node_config(self.name),
            "ibe_secret": self.ibe_secret,
            "ibe_param_shard": self.public_param_shard,
            "is_client": True,
        }
