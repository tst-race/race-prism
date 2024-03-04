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
from typing import *

import structlog
from jaeger_client import SpanContext

from prism.common.logging import MONITOR_STATUS
from prism.common.message import PrismMessage, TypeEnum
from prism.common.tracing import trace_context
from prism.common.transport.epoch_transport import EpochTransport
from prism.common.transport.hooks import MessageTypeHook
from prism.common.util import bytes_hex_abbrv
from prism.server.routing import Router


class EARKStore:
    def __init__(self, own_pseudonym: bytes, transport: EpochTransport, router: Router):
        self.epoch = transport.epoch
        self.router = router
        self._transport = transport
        self._database: Dict[bytes, PrismMessage] = {}
        self._logger = structlog.getLogger(__name__).bind(myself=bytes_hex_abbrv(own_pseudonym), epoch=self.epoch)
        self._monitor_logger = structlog.get_logger(MONITOR_STATUS).bind(
            myself=bytes_hex_abbrv(own_pseudonym),
            epoch=self.epoch,
        )

    def __len__(self):
        return len(self._database)

    @property
    def payloads(self) -> List[PrismMessage]:
        return list(self._database.values())

    async def initiate(self, payload: PrismMessage):
        """ Initiate the flooding of given payload from this server. """
        assert payload
        with trace_context(self._logger, "flood-initiated", epoch=self.epoch) as scope:
            scope.debug(f"Initiate FLOODING for epoch={self.epoch}")
            carrier = PrismMessage(msg_type=TypeEnum.EPOCH_ARK_WRAPPER, sub_msg=payload, epoch=self.epoch)
            await self.router.flood(carrier, scope.context)

    async def handle_msg(self, message: PrismMessage, context: SpanContext):
        if message.pseudonym in self._database:
            return

        self._database[message.pseudonym] = message
        with trace_context(self._monitor_logger, "flood-stored", context, epoch=self.epoch, db_size=len(self)) as scope:
            scope.info(f'FLOODING database for epoch={self.epoch} has {len(self)} entries',
                       epoch=self.epoch,
                       originators=sorted([bytes_hex_abbrv(o) for o in self._database.keys()]),
                       n_db=len(self),)

    async def flood_listen_loop(self):
        self._logger.debug(f'Starting Flooding listen task')
        flood_hook = MessageTypeHook(None, TypeEnum.EPOCH_ARK_WRAPPER)
        await self._transport.register_hook(flood_hook)
        while True:
            package = await flood_hook.receive_pkg()
            inner = package.message.sub_msg
            await self.handle_msg(cast(PrismMessage, inner), package.context)

    def debug_dump(self, logger):
        earks = sorted(self.payloads, key=lambda e: e.name)
        logger.debug("EARKs flooded by previous roles:")
        for eark in earks:
            logger.debug(f"  {eark.name}, {eark.role}, {eark.committee}")
