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
from datetime import datetime
from typing import Dict, List, Optional

import trio
from jaeger_client import SpanContext

from .announcing_role import AnnouncingRole
from prism.common.transport.transport import Link
from prism.common.message import PrismMessage, TypeEnum, LinkAddress
from prism.common.config import configuration
from prism.common.tracing import inject_span_context, extract_span_context


class MessageStore:
    store: Dict[bytes, List[PrismMessage]]

    def __init__(self):
        self.message_store = {}

    def store(self, pseudonym: bytes, message: PrismMessage, context: SpanContext):
        message = inject_span_context(message, context)

        if pseudonym in self.message_store:
            self.message_store[pseudonym].append(message)
        else:
            self.message_store[pseudonym] = [message]

    @property
    def size(self) -> int:
        return sum(len(messages) for messages in self.message_store.values())

    def retrieve(self, pseudonym: bytes) -> List[PrismMessage]:
        return self.message_store.pop(pseudonym, [])


@dataclass
class Poll:
    nonce: bytes
    pseudonym: bytes
    expiration: Optional[datetime]
    context: SpanContext
    link_addresses: List[LinkAddress]
    links: List[Link] = field(default_factory=list)

    @property
    def live(self) -> bool:
        return (not self.expiration) or (self.expiration > datetime.utcnow())

    @property
    def trace(self) -> str:
        return self.context and hex(self.context.trace_id)[2:]

    @staticmethod
    def from_message(message: PrismMessage, context: SpanContext) -> Poll:
        assert message.msg_type == TypeEnum.READ_DROPBOX

        if message.expiration:
            expiration = datetime.utcfromtimestamp(message.expiration)
        else:
            expiration = None

        addresses = message.link_addresses or []

        return Poll(
            nonce=message.nonce,
            pseudonym=message.pseudonym,
            expiration=expiration,
            context=context,
            link_addresses=addresses
        )


class DropboxSS(AnnouncingRole, registry_name='DROPBOX'):
    def __init__(self, **kwargs):
        super().__init__(broadcast_tags={"downlink"}, **kwargs)
        self.store = MessageStore()
        self.active_polls = 0

    def ark_data(self) -> dict:
        d = super().ark_data()
        d['dropbox_index'] = self.server_data.dropbox_index
        return d

    def monitor_data(self) -> dict:
        return {
            **super().monitor_data(),
            "dropbox_stored_count": self.store.size,
            "active_polls": self.active_polls,
        }

    @property
    def ark_broadcasting(self) -> bool:
        return False

    async def dropbox_handler(self, nursery: trio.Nursery, decrypted: PrismMessage, context: SpanContext):
        if decrypted.msg_type == TypeEnum.READ_DROPBOX:
            nursery.start_soon(self.poll_task, decrypted, context)
        elif decrypted.msg_type == TypeEnum.WRITE_DROPBOX:
            nursery.start_soon(self.write, decrypted, context)

    async def poll_task(self, poll_message: PrismMessage, context: SpanContext):
        with self.trace("poll", context) as scope:
            poll = Poll.from_message(poll_message, scope.context)
            scope.debug(f"POLL: Poll request {poll.nonce.hex()[:6]} started.", expiration=poll.expiration)
            self.active_polls += 1

            while poll.live:
                await self.read_task(poll)

                if not poll.expiration:
                    break

                await trio.sleep(1.0)

            scope.debug(f"POLL: Poll request {poll.nonce.hex()[:6]} ended.")
            self.active_polls -= 1

            for link in poll.links:
                scope.debug(f"Closing link {link}")
                await link.close()
                scope.debug("Link closed")

    async def load_return_addresses(self, poll: Poll):
        if poll.link_addresses and not poll.links:
            for address in poll.link_addresses:
                link = await self._transport.load_address(address, [poll.nonce.hex()])
                if link:
                    self._logger.debug(f"POLL: Loaded link {link}")
                    poll.links.append(link)
                else:
                    self._logger.debug(f"POLL: Failed to load link address {address}")

    async def read_task(self, poll: Poll):
        messages = self.store.retrieve(poll.pseudonym)
        if not messages:
            return

        await self.load_return_addresses(poll)

        with self.trace("retrieve-dropbox", poll.context, retrieved_msgs=len(messages)) as retrieve_scope:
            retrieve_scope.info(f"retrieved {len(messages)} messages for pseudonym {poll.pseudonym.hex()}")
            for message in messages:
                if not await self.reply_to_client(poll, message, retrieve_scope.context):
                    retrieve_scope.error("FWD: Forwarding message failed, re-storing.")
                    self.store.store(poll.pseudonym, message, retrieve_scope.context)

    async def reply_on_link(self, link_address: LinkAddress, event: trio.Event, message: PrismMessage, context: SpanContext):
        if await self.router.send(link_address, message, context, block=True):
            event.set()

    async def reply_to_client(self, poll: Poll, reply: PrismMessage, retrieve_context: SpanContext):
        message_context = extract_span_context(reply)
        with self.trace("fwd-message", message_context, retrieve_context) as fwd_scope:
            if poll.links:
                # Attempt to send on each of the links provided by the client.
                # Return True immediately if one succeeds.
                success = trio.Event()
                with trio.move_on_after(configuration.db_reply_timeout) as cancel_scope:
                    async with trio.open_nursery() as nursery:
                        for link_address in poll.link_addresses:
                            nursery.start_soon(self.reply_on_link, link_address, success, reply, fwd_scope.context)

                        await success.wait()
                        cancel_scope.cancel()
                return success.is_set()
            else:
                return await self.router.broadcast(
                    reply,
                    fwd_scope.context,
                    timeout_ms=int(1000 * configuration.db_reply_timeout),
                    block=True,
                )

    async def write(self, decrypted: PrismMessage, context: SpanContext):
        pseudonym = decrypted.pseudonym.hex()
        submessage = PrismMessage.from_cbor_dict(decrypted.sub_msg.as_cbor_dict())
        with self.trace("save-dropbox", context, pseudonym=pseudonym) as scope:
            self.store.store(decrypted.pseudonym, submessage, scope.context)
            scope.info(f"saving pseudonym {pseudonym} -> submessage {submessage}")

    async def main(self):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)
            nursery.start_soon(self.handler_loop, nursery, self.dropbox_handler, True, TypeEnum.ENCRYPT_DROPBOX_MESSAGE)
