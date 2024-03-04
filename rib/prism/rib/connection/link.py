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
from typing import Dict, List, Optional

import trio
from jaeger_client import SpanContext

from prism.common.config import configuration
from prism.common.constant import TIMEOUT_MS_MAX
from prism.common.message import PrismMessage
from prism.common.transport.enums import *
from prism.common.transport.transport import Link, Channel
from prism.rib.Log import logDebug, logError
from prism.rib.connection.state import TransportState
from networkManagerPluginBindings import LinkProperties, IRaceSdkNM, ChannelProperties, EncPkg, sdkStatusToString, SDK_OK


class CommsLink(Link):
    channel: CommsChannel
    properties: LinkProperties
    link_address: str
    link_type: LinkType

    def __init__(self, link_id: str, channel: CommsChannel, properties: LinkProperties):
        super().__init__(link_id)
        self.race = channel.race
        self.replay = channel.replay
        self.transport_state = channel.transport_state
        self.channel = channel
        self.link_type = LinkType(properties.linkType)
        self.update_properties(properties)
        self.connection_id = None
        self.manually_closed = False
        self.failures = 0
        self.endpoints = list(self.race.getPersonasForLink(link_id))

    def open_handle(self, link_type: Optional[LinkType] = None) -> int:
        send_timeout = configuration.transport_send_timeout
        open_timeout = configuration.transport_open_connection_timeout
        logDebug(f"Opening connection on {self}")
        response = self.race.openConnection(
            linkType=(link_type or self.link_type).value,
            linkId=self.link_id,
            linkHints="{}",
            priority=1,
            sendTimeout=send_timeout,
            timeout=open_timeout
        )
        if not response.status == SDK_OK:
            logError(f"Open connection on {self} failed: {sdkStatusToString(response.status)}")
            # TODO - more error handling
            return -1
        logDebug(f"Handle: {response.handle}")
        return response.handle

    async def open(self, link_type: Optional[LinkType] = None, timeout_ms: int = TIMEOUT_MS_MAX) -> bool:
        self.manually_closed = False
        handle = self.open_handle(link_type)
        self.transport_state.handle_links[handle] = self

        with trio.move_on_after(timeout_ms / 1000):
            while not self.active:
                await trio.sleep(0.1)
            return True

        # noinspection PyUnreachableCode
        return False

    async def close(self):
        self.manually_closed = True
        if self.connection_id:
            self.race.closeConnection(self.connection_id, 120)

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = TIMEOUT_MS_MAX) -> bool:
        if not self.connection_id or self.connection_status not in [ConnectionStatus.OPEN, ConnectionStatus.AVAILABLE]:
            return False

        self.pending_sends += 1
        message = message.clone(transport_timestamp=int(datetime.utcnow().timestamp()))

        if context:
            pkg = EncPkg(context.trace_id, context.span_id, message.encode())
        else:
            pkg = EncPkg(0, 0, message.encode())
        pkg = self.transport_state.checksum.add_checksum(pkg)

        if not configuration.get("transport_use_sdk_timeout", False):
            sdk_timeout = 0
        else:
            sdk_timeout = timeout_ms

        response = self.race.sendEncryptedPackage(pkg, self.connection_id, 0, sdk_timeout)
        self.channel.queue_size = response.queueUtilization
        if not response.status == SDK_OK:
            logError(f"Error sending message on {self}: {sdkStatusToString(response.status)}")
            self.pending_sends -= 1
            return False

        handle = response.handle
        if self.endpoints:
            receiver = self.endpoints[0]
        else:
            receiver = "unknown"
        self.channel.replay.log(receiver, self, bytes(pkg.getCipherText()), pkg.getTraceId(), handle)

        # TODO - remove trio timeout if SDK timeout is reliable
        with trio.move_on_after(timeout_ms / 1000):
            while True:
                if handle in self.transport_state.successful_packages:
                    self.last_send = datetime.utcnow()
                    self.pending_sends -= 1
                    return True
                if handle in self.transport_state.failed_packages:
                    self.pending_sends -= 1
                    return False
                await trio.sleep(0.05)

        # noinspection PyUnreachableCode
        self.pending_sends -= 1
        return False

    def update_properties(self, properties):
        self.properties = properties
        self.link_address = properties.linkAddress


class CommsChannel(Channel):
    _links: Dict[str, CommsLink]
    transport_state: TransportState

    def __init__(
        self, race: IRaceSdkNM, transport_state: TransportState, properties: ChannelProperties
    ):
        super().__init__(properties.channelGid)
        self._links = {}
        self.race = race
        self.transport_state = transport_state
        self.replay = transport_state.replay
        self.status = ChannelStatus(properties.channelStatus)

        self.link_direction = LinkDirection(properties.linkDirection)
        self.transmission_type = TransmissionType(properties.transmissionType)
        self.connection_type = ConnectionType(properties.connectionType)
        self.reliable = properties.reliable
        self.mtu = properties.mtu
        self.queue_size = 0

        self.bandwidth_bps = min(
            properties.loaderExpected.send.bandwidth_bps,
            properties.loaderExpected.receive.bandwidth_bps,
            properties.creatorExpected.send.bandwidth_bps,
            properties.creatorExpected.receive.bandwidth_bps,
        )

        self.latency_ms = max(
            properties.loaderExpected.send.latency_ms,
            properties.loaderExpected.receive.latency_ms,
            properties.creatorExpected.send.latency_ms,
            properties.creatorExpected.receive.latency_ms,
        )

        self.loss = max(
            properties.loaderExpected.send.loss,
            properties.loaderExpected.receive.loss,
            properties.creatorExpected.send.loss,
            properties.creatorExpected.receive.loss,
        )

    @property
    def links(self) -> List[CommsLink]:
        return list(self._links.values())

    async def create_link(self, endpoints: List[str]) -> Optional[Link]:
        if not self.status.usable:
            logDebug(f"CL: Requested create_link on channel {self.channel_id} with status {self.status}")
            return None

        logDebug(f"CL: Requested to create link on channel {self} to endpoints {endpoints}")
        response = self.race.createLink(self.channel_id, endpoints, 0)
        if not response.status == SDK_OK:
            logError(f"CL: createLink failed: {sdkStatusToString(response.status)}")
        link = await self._await_link(response.handle)
        if not link:
            return None

        link.role = "creator"
        return link

    async def load_link(
            self,
            link_address: str,
            endpoints: List[str],
            link_type: Optional[LinkType],
            role: str = "loader",
    ) -> Optional[Link]:
        if not self.status.usable:
            logDebug(f"CL: Requested load_link on channel {self.channel_id} with status {self.status}")
            return None

        handle = self.load_address(link_address, endpoints, role)
        if not handle:
            return None

        link = await self._await_link(handle, link_type)
        if not link:
            return None

        link.role = role

        if not link.link_address:
            link.link_address = link_address
        return link

    def load_address(self, link_address: str, endpoints: List[str], role: str) -> int:
        if role == "creator":
            response = self.race.createLinkFromAddress(self.channel_id, link_address, endpoints, 0)
        else:
            response = self.race.loadLinkAddress(self.channel_id, link_address, endpoints, 0)

        if not response.status == SDK_OK:
            logError(f"Loading address {link_address} failed: {sdkStatusToString(response.status)}")

        return response.handle

    async def _await_link(self, handle: int, link_type: Optional[LinkType] = None) -> Link:
        while True:
            if handle in self.transport_state.handle_links:
                # noinspection PyTypeChecker
                link: CommsLink = self.transport_state.handle_links[handle]
                await link.open(link_type)
                return link

            await trio.sleep(0.2)

    def add_link(self, link: CommsLink):
        self._links[link.link_id] = link
