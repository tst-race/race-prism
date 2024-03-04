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
from time import time
from typing import Optional, List, Set

from prism.common.message import PrismMessage, TypeEnum
from prism.common.server_db import ServerDB, ServerRecord
from prism.common.state import StateStore
from prism.server.server_data import ServerData


class ArkStore(ServerDB):
    def __init__(self, state_store: StateStore, epoch: str, pseudonym: bytes):
        super().__init__(state_store, epoch)
        self.own_pseudonym = pseudonym
        self.reachable_pseudonyms: Set[bytes] = set()

    @property
    def own_ark(self):
        record = self.servers.get(self.own_pseudonym)

        if record:
            return record.ark
        else:
            return None

    def record(self, ark: PrismMessage, rebroadcast=False):
        rec = super().record(ark)
        if not rec.valid():
            self.remove(rec.pseudonym)

        if rebroadcast:
            rec.last_broadcast = datetime.utcfromtimestamp(0)

    @property
    def reachable_servers(self) -> List[ServerRecord]:
        return [s for s in self.valid_servers if s.pseudonym in self.reachable_pseudonyms]

    @property
    def unreachable_servers(self) -> List[ServerRecord]:
        return [s for s in self.valid_servers if s.pseudonym not in self.reachable_pseudonyms]

    def promote(self, pseudonym: bytes):
        """If record for this pseudonym exists, promote it in queue by setting last_broadcast to datetime.min + 1"""
        rec = self.servers.get(pseudonym, None)
        if rec is not None:
            rec.last_broadcast = datetime.utcfromtimestamp(0) + timedelta(seconds=1)

    def remove(self, pseudonym: bytes):
        """Remove entry for given pseudonym (if it exists)"""
        self.servers.pop(pseudonym, None)

    def save(self):
        # The server ARK store should not save its state. It will be rebuilt from LSP
        # after a restart
        pass

    def broadcast_message(self, server_data: ServerData, mtu: int, reachable=True) -> Optional[PrismMessage]:
        """Finds the batch_size least recently broadcast ARKs, updates their broadcast time, and returns an ARKS message
        to be sent out."""
        if reachable:
            server_pool = self.reachable_servers
        else:
            server_pool = self.valid_servers

        non_dummy_servers = [server for server in server_pool if server.role != "DUMMY" and not server.ark.degraded]
        dead_servers = [s.pseudonym for s in self.unreachable_servers if s.role != "DUMMY"]
        degraded_servers = [s.pseudonym for s in server_pool if s.ark.degraded]
        dead_servers.extend(degraded_servers)

        records_by_last_broadcast = sorted(non_dummy_servers, key=lambda s: s.last_broadcast)
        batch = []
        message = None
        new_size = 0

        for batch_size in range(1, len(records_by_last_broadcast) + 1):
            new_batch = records_by_last_broadcast[:batch_size]
            new_message = PrismMessage(
                msg_type=TypeEnum.ARKS,
                pseudonym=server_data.pseudonym,
                epoch=server_data.epoch,
                micro_timestamp=int(time() * 1e6),
                submessages=[rec.ark for rec in new_batch],
                dead_servers=dead_servers,
            )
            new_size = len(new_message.encode())

            if new_size > mtu:
                break
            else:
                batch = new_batch
                message = new_message

        if new_size and message is None:
            self.logger.warning(f"Single ARK produces message size ({new_size}) greater than MTU {mtu}.")

        for rec in batch:
            rec.last_broadcast = datetime.utcnow()

        return message
