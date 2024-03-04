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

from datetime import datetime
from typing import List, Optional

from jaeger_client import SpanContext

from prism.common.constant import TIMEOUT_MS_MAX
from prism.common.message import LinkAddress, PrismMessage
from prism.common.transport.enums import LinkStatus, LinkType
from prism.common.transport.transport import Transport, Channel, Link, MessageHook, Package, LocalLink


class EpochMessageHook(MessageHook):
    def __init__(self, inner_hook: MessageHook, epoch: str):
        super().__init__()
        self.inner_hook = inner_hook
        self.epoch = epoch

    def match(self, package: Package) -> bool:
        if package.message.epoch and not package.message.epoch == self.epoch:
            return False

        return self.inner_hook.match(package)

    async def put(self, package: Package):
        await self.inner_hook.put(package)

    def __repr__(self):
        return f"EpochHook({self.epoch}, {self.inner_hook})"

    def dispose(self):
        super().dispose()
        self.inner_hook.dispose()


class EpochTransport(Transport):
    def __init__(self, transport: Transport, epoch: str):
        super().__init__(transport.configuration)
        self.epoch = epoch
        self.inner_transport = transport
        self._hook_map = {}
        self.local_address = transport.local_address
        self.local_link = EpochLink(LocalLink(self), self)
        self.epoch_links: List[EpochLink] = []

    @property
    def raw_links(self):
        """
        Returns all the raw, unwrapped links from the underlying transport.
        Avoid using except when absolutely necessary.
        """
        return [link for channel in self.inner_transport.channels for link in channel.links]

    def promote(self, link: Link):
        """
        Promote a raw link into a real link for this epoch.
        """
        if isinstance(link, EpochLink):
            if link.epoch == self:
                return link
            else:
                return self.promote(link.inner_link)

        link = EpochLink(link, self)
        self.epoch_links.append(link)
        return link

    @property
    def overhead_bytes(self):
        return self.inner_transport.overhead_bytes + len(self.epoch) + 10

    @property
    def channels(self) -> List[Channel]:
        return [EpochChannel(channel, self) for channel in self.inner_transport.channels]

    async def register_hook(self, hook: MessageHook):
        epoch_hook = EpochMessageHook(hook, self.epoch)
        await self.inner_transport.register_hook(epoch_hook)
        self._hook_map[id(hook)] = epoch_hook

    def remove_hook(self, hook: MessageHook):
        epoch_hook = self._hook_map[id(hook)]
        self.inner_transport.remove_hook(epoch_hook)
        del self._hook_map[id(hook)]

    async def submit_to_hooks(self, package: Package):
        await self.inner_transport.submit_to_hooks(package)

    async def shutdown(self):
        for link in self.epoch_links:
            await link.close()


class EpochChannel(Channel):
    """
    A thin, ephemeral wrapper around an ordinary Transport which converts its links to EpochLinks.
    """
    def __init__(self, channel: Channel, epoch_transport: EpochTransport):
        super().__init__(channel.channel_id)
        self._inner_channel = channel
        self.epoch_transport = epoch_transport
        self.epoch = epoch_transport.epoch
        self.link_direction = channel.link_direction
        self.transmission_type = channel.transmission_type
        self.connection_type = channel.connection_type
        self.reliable = channel.reliable
        self.mtu = channel.mtu
        self.bandwidth_bps = channel.bandwidth_bps
        self.latency_ms = channel.latency_ms
        self.loss = channel.loss
        self.tags = channel.tags

    def __repr__(self):
        return repr(self._inner_channel)

    @property
    def status(self):
        return self._inner_channel.status

    @property
    def links(self) -> List[Link]:
        return [link for link in self.epoch_transport.epoch_links if link.channel.channel_id == self.channel_id]

    async def create_link(self, endpoints: List[str]) -> Optional[Link]:
        new_link = await self._inner_channel.create_link(endpoints)

        if not new_link:
            return None

        epoch_link = EpochLink(new_link, self.epoch_transport)
        self.epoch_transport.epoch_links.append(epoch_link)
        return epoch_link

    async def load_link(self, link_address: str, endpoints: List[str], link_type: Optional[LinkType], role: Optional[str]) -> Optional[Link]:
        matches = [link for link in self._inner_channel.links
                   if link.link_address == link_address and link.link_status == LinkStatus.LOADED and link.active]

        if not matches:
            new_link = await self._inner_channel.load_link(link_address, endpoints, link_type, role)
            matches.append(new_link)

        if not matches:
            return None

        epoch_link = EpochLink(matches[0], self.epoch_transport)
        self.epoch_transport.epoch_links.append(epoch_link)
        return epoch_link


class EpochLink(Link):
    def __init__(self, link: Link, epoch_transport: EpochTransport):
        super().__init__(link.link_id)
        self.inner_link = link
        self.epoch_transport = epoch_transport
        self.epoch = epoch_transport.epoch
        self.last_send = datetime.utcfromtimestamp(0)
        self.last_receive = datetime.utcfromtimestamp(0)
        self.endpoints = link.endpoints
        self.inner_link.references.append(self)
        self.link_type = link.link_type
        self.channel = link.channel
        self.role = link.role

    def __str__(self):
        return str(self.inner_link)

    @property
    def link_address(self):
        return self.inner_link.link_address

    @property
    def can_send(self) -> bool:
        return self.inner_link.can_send

    def can_reach(self, address: str) -> bool:
        return self.inner_link.can_reach(address)

    @property
    def active(self) -> bool:
        return self.inner_link.active

    @property
    def address_cbor(self) -> LinkAddress:
        return self.inner_link.address_cbor

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = TIMEOUT_MS_MAX) -> bool:
        self.pending_sends += 1
        message = message.clone(epoch=self.epoch)
        result = await self.inner_link.send(message, context, timeout_ms)
        if result:
            self.last_send = datetime.utcnow()
        self.pending_sends -= 1
        return result

    async def open(self):
        if self not in self.inner_link.references:
            self.inner_link.references.append(self)
        if self not in self.epoch_transport.epoch_links:
            self.epoch_transport.epoch_links.append(self)

    async def close(self):
        if self in self.inner_link.references:
            self.inner_link.references.remove(self)
        if self in self.epoch_transport.epoch_links:
            self.epoch_transport.epoch_links.remove(self)
