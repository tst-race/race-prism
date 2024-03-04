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
from typing import Tuple, List

import trio
from jaeger_client import SpanContext

from prism.common.config import configuration
from prism.common.message import PrismMessage, TypeEnum
from prism.common.vrf.link import is_link_compatible
from .announcing_role import AnnouncingRole
from ...mixing.mix_strategies import get_mix


class Emix(AnnouncingRole, registry_name='EMIX'):
    def __init__(self, **kwargs):
        super().__init__(broadcast_tags={"ark"}, uplink=True, **kwargs)
        self.mix_strategy = get_mix(configuration.get('mix_strategy'), self)  # will choose DEFAULT if not specified

    def ark_data(self) -> dict:
        return {
            **super().ark_data(),
            "link_addresses": [link.address_cbor for link in self.router.uplink_links],
        }

    async def mix_handler(self, nursery: trio.Nursery, message: PrismMessage, context: SpanContext):
        if message.msg_type == TypeEnum.LINK_REQUEST:
            nursery.start_soon(self.handle_client_link_request, context, message)
        else:
            submessage = PrismMessage.from_cbor_dict(message.sub_msg.as_cbor_dict())
            nursery.start_soon(self.mix_message, context, message, submessage)

    async def mix_message(self, context: SpanContext, decrypted: PrismMessage, submessage: PrismMessage):
        assert (decrypted.msg_type == TypeEnum.SEND_TO_EMIX and
                submessage.msg_type == TypeEnum.ENCRYPT_EMIX_MESSAGE) or \
               (decrypted.msg_type == TypeEnum.SEND_TO_DROPBOX and
                submessage.msg_type == TypeEnum.ENCRYPT_DROPBOX_MESSAGE)

        context = await self.mix_strategy.mix(submessage, context)

        with self.trace("mix-forward", context) as scope:
            retries = 0
            while not await self.router.send(submessage.pseudonym,
                                             submessage,
                                             context=scope.context) \
                    and retries < configuration.mix_forward_retry_limit:
                scope.warning(f"Failed to emit message over next hop. "
                                     f"Retrying in {configuration.mix_forward_retry_delay_sec}s.")
                await trio.sleep(configuration.mix_forward_retry_delay_sec)
                retries += 1

            if retries >= configuration.mix_forward_retry_limit:
                scope.error(f"Could not forward message after {retries} attempts. Giving up.")

    async def handle_client_link_request(self, context: SpanContext, decrypted: PrismMessage):
        with self.trace("link-request", context) as scope:
            scope.debug(f"Loading {len(decrypted.link_addresses)} link(s) to {decrypted.name}")
            for address in decrypted.link_addresses:
                await self.router.add_broadcast_client(address, decrypted.name)

    def link_targets(self, seed: int) -> List[Tuple[PrismMessage, str]]:
        emixes = sorted([server for server in self.previous_role.flooding.payloads
                         if server.role == "EMIX"],
                        key=lambda s: s.pseudonym.hex())

        targets = set()

        probability = configuration.vrf_link_probability
        vrf_targets = [emix.pseudonym for emix in emixes
                       if is_link_compatible(self.pseudonym, emix.pseudonym, probability)]
        targets.update(vrf_targets)

        if configuration.vrf_topology_ring:
            my_index = next(i for i, emix in enumerate(emixes) if emix.pseudonym == self.pseudonym)
            ring_targets = [emixes[(my_index - 1) % len(emixes)].pseudonym,
                            emixes[(my_index + 1) % len(emixes)].pseudonym]
            targets.update(ring_targets)

        return [(emix, "lsp") for emix in emixes if emix.pseudonym in targets]

    async def main(self, caller_nursery: trio.Nursery = None) -> None:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)
            nursery.start_soon(self.handler_loop, nursery, self.mix_handler, True, TypeEnum.ENCRYPT_EMIX_MESSAGE)
