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
from time import time
from typing import Optional, Set, Dict

import trio
from networkx import shortest_path, DiGraph

from prism.common.logging import get_logger
from prism.common.message import PrismMessage
from prism.common.tracing import trace_context
from prism.server.CS2.ark_store import ArkStore
from prism.server.routing.neighborhood import Neighborhood


class LinkStateNetwork:
    def __init__(self, pseudonym: bytes, epoch: str, neighborhood: Neighborhood, ark_store: ArkStore):
        self.logger = get_logger(__name__, epoch=epoch)
        self.epoch = epoch
        self.pseudonym = pseudonym
        self.neighborhood = neighborhood
        self.ark_store = ark_store
        self.database: Dict[bytes, PrismMessage] = {}
        self.routing_table: Dict[bytes, bytes] = {}

    def __len__(self):
        return len(self.database)

    def debug_string(self):
        s = "Routing table:\n"
        for src, dst in self.routing_table.items():
            s += f"  {src.hex()} -> {dst.hex()}\n"
        return s

    def update(self, lsp: PrismMessage) -> bool:
        original = self.database.get(lsp.pseudonym)
        if original and original.micro_timestamp >= lsp.micro_timestamp:
            return False

        self.database[lsp.pseudonym] = lsp
        self._update_routing_table()
        return True

    def _update_routing_table(self):
        previously_reachable = set(self.routing_table.keys())

        cost_by_directional_edges = {
            (source, neighbor.pseudonym): neighbor.cost
            for source, lsp in self.database.items()
            for neighbor in lsp.neighbors
            if (lsp.micro_timestamp / 1e6) + lsp.ttl > time()
        }

        graph = DiGraph()

        for (src, dst), cost in cost_by_directional_edges.items():
            graph.add_weighted_edges_from([(src, dst, cost)])

        if not graph.has_node(self.pseudonym):
            return

        paths = shortest_path(graph, source=self.pseudonym)
        self.routing_table = {target: path[1] for target, path in paths.items()
                              if len(path) > 1 and target != self.pseudonym}

        now_reachable = set(self.routing_table.keys())
        self.ark_store.reachable_pseudonyms = now_reachable.union({self.pseudonym})
        if now_reachable != previously_reachable:
            with trace_context(self.logger,
                               "updated-LS-table",
                               epoch=self.epoch,
                               lsp_table_size=len(self.routing_table)):
                pass

    def _remove_expired(self):
        expired = []
        for source, lsp in self.database.items():
            if (lsp.micro_timestamp / 1e6) + lsp.ttl < time():
                expired.append(source)

        if expired:
            for source in expired:
                del self.database[source]
            self._update_routing_table()

    def hop(self, destination: bytes) -> Optional[bytes]:
        if destination in self.neighborhood and self.neighborhood[destination].online:
            return destination

        return self.routing_table.get(destination)

    def reachable(self) -> Set[bytes]:
        """Returns a list of all reachable endpoints."""
        return set(self.routing_table.keys())

    async def run(self):
        while True:
            self._remove_expired()
            await trio.sleep(30.0)

    def debug_dump(self, logger):
        logger.debug("Routing table:")
        for src, dst in self.routing_table.items():
            logger.debug(f"  {src.hex()[:6]} -> {dst.hex()[:6]}")
        logger.debug("\n")

        logger.debug("LS Database:")
        for src, lsp in self.database.items():
            logger.debug(f"  {src.hex()[:6]} -> {lsp.name} ({lsp.pseudonym.hex()[:6]}, epoch: {lsp.epoch}")
            logger.debug(f"            {lsp.neighbors}")
        logger.debug("\n")
