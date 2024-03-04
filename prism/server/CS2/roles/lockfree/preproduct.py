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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import trio

from prism.common.state import StateStore
from prism.common.util import frequency_limit
from prism.server.CS2.roles.lockfree.peer import Peer
from prism.common.config import configuration
from prism.common.message import Share, PreproductInfo


@dataclass
class Triple:
    """
    Shares of a Beaver triple, comprised of random numbers a, b, and c=a*b.
    Used for degree reduction in MPC multiplication.
    """

    a: Share
    b: Share
    c: Share

    def __repr__(self):
        return f"T({self.a}, {self.b}, {self.c})"

    def json(self) -> dict:
        return {
            "a": self.a.encode().hex(),
            "b": self.b.encode().hex(),
            "c": self.c.encode().hex(),
        }

    @classmethod
    def from_json(cls, j: dict):
        return Triple(
            a=Share.decode(bytes.fromhex(j["a"])),
            b=Share.decode(bytes.fromhex(j["b"])),
            c=Share.decode(bytes.fromhex(j["c"])),
        )


@dataclass
class PreproductChunk:
    """
    A chunk of preproducts to be used in a single MPC operation.
    """

    triples: List[Triple]
    random_numbers: List[Share]

    def __repr__(self):
        return f"Preproducts({self.triples}, {self.random_numbers})"

    def json(self) -> dict:
        return {
            "triples": [t.json() for t in self.triples],
            "random_numbers": [r.json() for r in self.random_numbers],
        }

    @property
    def size(self) -> int:
        return len(self.triples)


@dataclass
class PreproductBatch:
    """
    A batch of MPC preproducts from which chunks can be claimed to use in operations by the batch's owner.
    Exists in parallel on all participating peers.
    """

    batch_id: bytes
    peers: Set[str]
    owned: bool

    triples: List[Optional[Triple]]
    random_numbers: List[Optional[Share]]

    next: int = field(default=0)

    def __repr__(self) -> str:
        return f"{'*' if self.owned else ''}" \
               f"Batch({self.batch_id.hex()[:6]}, {self.peers}, {self.remaining}/{len(self.random_numbers)})"

    def json(self) -> dict:
        return {
            "batch_id": self.batch_id.hex(),
            "peers": list(self.peers),
            "owned": self.owned,
            "triples": [t.json() if t else None for t in self.triples],
            "random_numbers": [r.encode().hex() if r else None for r in self.random_numbers],
            "next": self.next,
        }

    @classmethod
    def from_json(cls, j: dict) -> PreproductBatch:
        return PreproductBatch(
            batch_id=bytes.fromhex(j["batch_id"]),
            peers=set(j["peers"]),
            owned=j["owned"],
            triples=[Triple.from_json(t) if t else None for t in j["triples"]],
            random_numbers=[Share.decode(bytes.fromhex(r)) if r else None for r in j["random_numbers"]],
            next=j["next"],
        )

    @property
    def size(self) -> int:
        return len(self.triples)

    def claim_chunk(self, size: int) -> Optional[Tuple[bytes, int, int]]:
        """
        Only for use by the owner of the batch.

        Return the next size unused preproducts from this batch, or None if there aren't enough preproducts remaining.
        """
        assert self.owned

        if size > self.remaining:
            return None

        chunk_info = (self.batch_id, self.next, size)

        self.next += size

        return chunk_info

    def get_chunk(self, start: int, size: int) -> Optional[PreproductChunk]:
        """
        Return the specified chunk of preproducts from this batch, and nulls them out to prevent double-fetching.
        """
        chunk = PreproductChunk(
            triples=self.triples[start : start + size],
            random_numbers=self.random_numbers[start : start + size],
        )

        for i in range(start, start + size):
            self.triples[i] = None
            self.random_numbers[i] = None

        if not all(chunk.triples) or not all(chunk.random_numbers):
            return None

        return chunk

    def serves(self, peers: List[Peer], exact: bool = False) -> bool:
        """Return true if all peers in the List are represented in this batch."""
        names = set(peer.name for peer in peers)

        if any(self.batch_id not in peer.preproduct_batches for peer in peers):
            return False

        if exact:
            return names == self.peers
        else:
            return self.peers.issuperset(names)

    @property
    def remaining(self) -> int:
        return max(0, self.size - self.next)


class PreproductStore:
    batches: Dict[bytes, PreproductBatch]

    def __init__(self, logger, mpc_logger, state_store: StateStore):
        self.state_store = state_store
        self.batches = {}
        self._logger = logger
        self._mpc_logger = mpc_logger

        self.load_state()

    async def claim_chunk(self, size: int, peers: List[Peer]) -> PreproductInfo:
        """
        Return a chunk of preproducts from a batch that includes the requested peers.
        If there is a smaller number than size available, it will return what is available.
        If there are none remaining, it will wait until some preproducts are available.
        """
        while True:
            if self.total_remaining(peers) == 0:
                if frequency_limit("preproduct_availability"):
                    self._logger.debug("Awaiting preproduct availability.")

                await trio.sleep(0.5)
                continue

            my_batches = sorted(
                [
                    batch
                    for batch in self.batches.values()
                    if batch.owned and batch.serves(peers) and batch.remaining >= 0
                ],
                key=lambda b: b.remaining,
                reverse=True,
            )

            batches = []
            starts = []
            sizes = []
            to_claim = size
            for batch in my_batches:
                batch_id, start, chunk_size = batch.claim_chunk(min(batch.remaining, to_claim))
                batches.append(batch_id)
                starts.append(start)
                sizes.append(chunk_size)

                to_claim -= chunk_size

                if to_claim <= 0:
                    break

            self.save_state()
            return PreproductInfo(batches, starts, sizes)

    def get_chunk(self, info: PreproductInfo) -> Optional[PreproductChunk]:
        triples = []
        random_numbers = []
        for batch_id, start, size in zip(info.batches, info.starts, info.sizes):
            if batch_id not in self.batches:
                return None
            chunk = self.batches[batch_id].get_chunk(start, size)
            if not chunk:
                return None
            triples.extend(chunk.triples)
            random_numbers.extend(chunk.random_numbers)

        return PreproductChunk(triples, random_numbers)

    def total_remaining(self, peers: List[Peer], exact: bool = False) -> int:
        def valid_batch(batch: PreproductBatch) -> bool:
            return (
                batch.owned
                and batch.serves(peers, exact=exact)
                and all(batch.batch_id in peer.preproduct_batches for peer in peers)
            )

        return sum(batch.remaining for batch in self.batches.values() if valid_batch(batch))

    def add_batch(self, batch: PreproductBatch):
        self.batches[batch.batch_id] = batch
        self.save_state()
        if configuration.debug_extra:
            self._mpc_logger.debug("Added batch", batch=batch.json())

    def save_state(self):
        d = {
            "batches": {
                batch_id.hex(): batch.json()
                for batch_id, batch in self.batches.items()
            }
        }

        self.state_store.save_state("preproduct", d)

    def load_state(self):
        state = self.state_store.load_state("preproduct")
        if not state:
            return

        self.batches = {
            bytes.fromhex(batch_id): PreproductBatch.from_json(batch)
            for batch_id, batch in state["batches"].items()
        }

    def debug_dump(self, logger):
        for batch in self.batches.values():
            logger.debug(f"  {batch}")
