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
import math
from abc import ABCMeta
from datetime import datetime, timedelta
from random import Random
from time import time
from typing import Tuple, List, Optional

import trio
from jaeger_client import SpanContext

from prism.common.config import configuration
from prism.common.crypto.verify import verify_ARK, sign_ARK
from prism.common.message import create_ARK, TypeEnum, PrismMessage
from prism.common.transport.transport import MessageHook, Package
from prism.common.vrf.link import is_link_compatible
from prism.common.vrf.sortition import VRFSortition
from ...CS2.ark_store import ArkStore
from ...CS2.roles.abstract_role import AbstractRole


class ArkHook(MessageHook):
    def __init__(self, server_data):
        super().__init__()
        self.server_data = server_data

    def match(self, package: Package) -> bool:
        msg = package.message
        # don't verify ARK here as we want to consume it even if it doesn't pass verification
        return msg.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY and self.server_data.pseudonym != msg.pseudonym


class AnnouncingRole(AbstractRole, metaclass=ABCMeta):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        assert self.server_data

        self._ark_hook = ArkHook(self.server_data)
        self.handoff_store: Optional[ArkStore] = None
        self._last_known = set()
        self.vrf_sortition: Optional[VRFSortition] = None

    def ark_data(self) -> dict:
        # can be overridden to add more parameters as needed by specific roles
        d = self.server_data.ark_data()
        d["broadcast_addresses"] = self.router.broadcast_addresses
        return d

    @property
    def ark_ready(self) -> bool:
        return True

    @property
    def ark_broadcasting(self) -> bool:
        return True

    def monitor_data(self) -> dict:
        return {
            "valid_ark_count": len(self.ark_store.valid_servers),
            "arking": self.ark_ready,
            **super().monitor_data()
        }

    async def ark_update_loop(self):
        self._logger.debug(f'Starting ARK update loop')

        last_ark_data = None
        last_update_time = datetime.min

        while True:
            if not self.ark_ready:
                await trio.sleep(1)
                continue

            ark_data = self.ark_data()
            if not ark_data:
                await trio.sleep(1)
                continue

            ark_interval = timedelta(seconds=max(math.ceil(configuration.cs2_ark_timeout * 60), 0))

            if ark_data == last_ark_data and datetime.utcnow() - last_update_time < ark_interval:
                await trio.sleep(1)
                continue

            last_ark_data = ark_data
            last_update_time = datetime.utcnow()

            expiration_factor = max(configuration.get('cs2_ark_expiration_factor', 1.0), 1)
            expiration = time() + ark_interval.total_seconds() * expiration_factor
            message = create_ARK(expiration=int(expiration), micro_timestamp=int(time() * 1e6), **ark_data)
            signed_ark = sign_ARK(message, self.server_key)

            self._logger.debug(f"Updated own ARK: {str(signed_ark)}")

            self.ark_store.record(signed_ark, True)
            self.update_known()

            await trio.sleep(1)

    async def ark_broadcast_loop(self):
        """In this task, we broadcast known ARKs at a fixed rate, prioritizing the ARKs we've broadcast least recently.
        Whenever our own ARK changes, we backdate its last broadcast to the beginning of time to put it at the head of
        the queue.

        Sub-classing roles can choose to turn off the emitting of ARKS if they set `ark_broadcasting` to False.
        """
        self._logger.debug(f'Starting ARK broadcast loop')
        while True:
            await trio.sleep(configuration.cs2_ark_sleep_time)
            self.update_known()

            if not self.ark_ready or not self.ark_broadcasting:
                continue

            if not self.router.broadcast_links:
                self._logger.warning("No links to broadcast ARKs on.")
                continue

            # In the handoff phase between epochs, start broadcasting ARKs from the new epoch
            if self.handoff_store:
                self._logger.debug("Broadcasting ARKs from next epoch")
                broadcast_store = self.handoff_store
            else:
                broadcast_store = self.ark_store

            ark_mtu = self.router.broadcast_mtu
            arks_message = broadcast_store.broadcast_message(self.server_data, mtu=ark_mtu)
            if not arks_message:
                self._logger.warning("No ARKs to broadcast.")
                continue

            ark_count = len(arks_message.submessages)
            ark_bytes = len(arks_message.encode())
            with self.trace(
                    "ark-broadcast",
                    ark_count=ark_count,
                    ark_mtu=ark_mtu,
                    ark_bytes=ark_bytes,
            ) as scope:
                scope.debug(f"Broadcasting {ark_count} ARKs {ark_bytes}B")
                await self.router.broadcast(arks_message, context=scope.context, block=True)

    def handoff_arks(self, new_ark_store: ArkStore):
        self.handoff_store = new_ark_store

    def update_known(self, parent_span_context: SpanContext = None):
        currently_known = self.ark_store.valid_servers
        current_set = {rec.pseudonym for rec in currently_known}
        known_str = ', '.join(f'{str(rec)}' for rec in currently_known)
        self._monitor_logger.info('update known servers', size=len(currently_known), known_servers=currently_known)
        if len(current_set.symmetric_difference(self._last_known)) > 0:
            with self.trace("currently-known-servers", parent_span_context, currently_known=len(currently_known)) \
                    as scope:
                scope.info(f'currently known servers ({len(currently_known)})' +
                           (f': [{known_str}]' if len(currently_known) < configuration.get("log_max_known", 6) else ''),
                           known_server_count=len(currently_known))
        self._last_known = current_set

    async def ark_listen_loop(self):
        self._logger.debug(f'Starting ARK listen loop')
        await self._transport.register_hook(self._ark_hook)
        while True:
            package = await self._ark_hook.receive_pkg()
            message = package.message
            if verify_ARK(message, self.vrf_sortition, self.root_certificate):
                self.ark_store.record(message)
                self.update_known(parent_span_context=package.context)
            else:
                self._logger.warning(f"Could not verify ARK {str(message)}")

    def link_targets(self, seed: int) -> List[Tuple[PrismMessage, str]]:
        """
        Returns a list of PrismMessages that contain pseudonym and link address information.
        By default, everybody wants to link to 3 compatible EMIXes.
        Override in subclasses to expand/replace link candidates.
        """

        probability = configuration.get("vrf_outer_link_probability")
        emixes = [server for server in self.previous_role.flooding.payloads
                  if server.role == "EMIX" and
                  is_link_compatible(self.pseudonym, server.pseudonym, probability)]
        Random(seed).shuffle(emixes)
        return [(emix, "lsp") for emix in emixes[:configuration.get("other_server_emix_links", 3)]]

    async def neighborhood_maintenance_loop(self):
        # Fixed random seed for stable sort
        seed = Random().randint(1, 2**64)
        while True:
            link_targets = self.link_targets(seed)
            for ark, tag in link_targets:
                self.neighborhood.update(ark.name, ark.pseudonym, ark.half_key.to_key(), ark.link_addresses, tag)

            await trio.sleep(1.0)

    async def main(self):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)
            if configuration.control_traffic:
                nursery.start_soon(self.ark_update_loop)
                nursery.start_soon(self.ark_listen_loop)
                nursery.start_soon(self.ark_broadcast_loop)
                if self.previous_role:
                    nursery.start_soon(self.neighborhood_maintenance_loop)
