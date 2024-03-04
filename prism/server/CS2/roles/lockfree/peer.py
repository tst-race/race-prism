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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Set

from prism.common.message import HalfKeyMap


@dataclass
class Peer:
    party_id: int
    name: str
    pseudonym: bytes = field(default=None)
    ready: bool = field(default=False)
    local: bool = field(default=False)
    last_hello_ack: datetime = field(default=None)
    last_ready_ack: datetime = field(default=None)
    preproduct_batches: Set[bytes] = field(default_factory=set)
    half_key: Optional[HalfKeyMap] = field(default=None)

    def __repr__(self) -> str:
        if self.pseudonym:
            ps = f", {self.pseudonym.hex()[:6]}"
        else:
            ps = ""
        return f"{'*' if self.local else ''}Peer({self.party_id}, {self.name}{ps})"

    def to_dict(self) -> dict:
        return {
            "party_id": self.party_id,
            "name": self.name,
            "pseudonym": self.pseudonym.hex(),
            "ready": self.ready,
            "local": self.local,
            "preproduct_batches": [batch_id.hex() for batch_id in self.preproduct_batches],
            "half_key": self.half_key.encode().hex() if self.half_key is not None else None,
        }


@dataclass
class DropboxPeer(Peer):
    stored_fragments: Set[bytes] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "stored_fragments": [fragment_id.hex() for fragment_id in self.stored_fragments],
        }

    @classmethod
    def from_dict(cls, d: dict):
        d["pseudonym"] = bytes.fromhex(d["pseudonym"])
        d["preproduct_batches"] = {bytes.fromhex(batch_id) for batch_id in d["preproduct_batches"]}
        if d["half_key"]:
            d["half_key"] = HalfKeyMap.decode(bytes.fromhex(d["half_key"]))
        d["stored_fragments"] = {bytes.fromhex(fragment_id) for fragment_id in d["stored_fragments"]}

        return DropboxPeer(**d)

    def __repr__(self) -> str:
        return "DB"+super().__repr__()
