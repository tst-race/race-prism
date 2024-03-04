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

import math
from datetime import datetime, timezone
from queue import Queue, Empty
from threading import Thread
from typing import List, Dict, Optional

import trio
from jaeger_client import SpanContext
from jaeger_client.constants import SAMPLED_FLAG

from prism.common.deduplicate import MessageDeduplicator
from prism.common.message import PrismMessage
from prism.common.replay import Replay
from prism.common.tracing import trace_context
from prism.common.transport.enums import ChannelStatus, ConnectionType, LinkStatus, ConnectionStatus
from prism.common.transport.transport import (
    Transport,
    Channel,
    Package,
)
from prism.rib.Log import logWarning, logDebug, logError
from prism.rib.connection.link import CommsChannel, CommsLink
from prism.rib.connection.state import TransportState
from prism.rib.error import CorruptPackageError
from networkManagerPluginBindings import (
    IRaceSdkNM,
    CONNECTION_OPEN,
    CONNECTION_CLOSED,
    CONNECTION_INVALID,
    PLUGIN_OK,
    PACKAGE_FAILED_NETWORK_ERROR,
    PACKAGE_FAILED_GENERIC,
    PACKAGE_INVALID,
    PACKAGE_RECEIVED,
    PACKAGE_SENT,
    PLUGIN_TEMP_ERROR,
    ChannelProperties,
    LinkProperties,
    PACKAGE_FAILED_TIMEOUT,
    EncPkg, SDK_OK, sdkStatusToString,
)


class CommsTransport(Transport):
    _channels: Dict[str, CommsChannel]
    race: IRaceSdkNM

    incoming_package_queue: Queue

    # Links by link_id
    links: Dict[str, CommsLink]
    # Links with open connections, by conn_id
    connection_links: Dict[str, CommsLink]

    flush_thread: Thread

    def __init__(
            self,
            configuration,
            race: IRaceSdkNM,
            replay: Replay,
    ):
        super().__init__(configuration)
        self._channels = {}
        self.race = race
        self.local_address = race.getActivePersona()

        self.incoming_package_queue = Queue()
        self.dead_link_queue = Queue()
        self.state = TransportState(replay)

        self.links = {}
        self.connection_links = {}

        self.running = True

        # A timestamp before which messages will be ignored if configuration.transport_ignore_old is True
        self.start_timestamp = int(datetime.now().timestamp()) - self.configuration.transport_ignore_tolerance

    @property
    def overhead_bytes(self) -> int:
        return self.state.checksum.checksum_bytes

    # ---------------
    # Startup Process
    # ---------------

    def start(self):
        """
        The Network Manager startup process involves enumerating available channels, activating the ones we want, and then loading
        genesis link addresses. This kicks off that process.
        """
        logDebug("CommsTransport.start()")

        self.enumerate_channels()
        self.channel_report()

        for channel in self._channels:
            response = self.race.activateChannel(channel, "default", 0)
            if not response.status == SDK_OK:
                logError(f"Error activating channel {channel}: {sdkStatusToString(response.status)}")

    def enumerate_channels(self):
        logDebug("Discovering channels")
        for channel in self.race.getAllChannelProperties():
            if channel.channelGid not in self._channels:
                self.create_channel(channel)

    def channel_report(self):
        logDebug("Channel Report")
        for channel in self._channels.values():
            logDebug(f"{channel}")

    def shutdown(self):
        self.running = False

    @property
    def channels(self) -> List[Channel]:
        return list(self._channels.values())

    async def run(self):
        logDebug(f"Start running CommsTransport...")
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().run)
            nursery.start_soon(self.package_task, nursery)
            nursery.start_soon(self.reconnect_task)
            nursery.start_soon(self.reaper_task)

    async def package_task(self, nursery: trio.Nursery):
        """
        A trio task to forward packages received from RACE to the PRISM side of the transport API.
        """
        seen = MessageDeduplicator(self.configuration)
        nursery.start_soon(seen.purge_task)
        while self.running:
            try:
                package = self.incoming_package_queue.get_nowait()

                if not seen.is_msg_new(package.message):
                    continue

                await self.submit_to_hooks(package)
            except Empty:
                pass
            await trio.sleep(0.01)

    async def reconnect_task(self):
        """
        A task to attempt to re-open dead links after a delay, with exponential backoff.
        """
        async with trio.open_nursery() as nursery:
            while self.running:
                try:
                    link = self.dead_link_queue.get_nowait()
                    nursery.start_soon(self.reconnect_delayed, link)
                except Empty:
                    pass
                await trio.sleep(1)

    async def reaper_task(self):
        """
        A task to reap links with no active reference or pending sends.
        """

        while self.running:
            await trio.sleep(1.0)

            if not self.configuration.transport_reaper:
                continue

            for channel in self.channels:
                for link in channel.links:
                    if link.disposable:
                        logDebug(f"Reaping unused link {link}")
                        await link.close()

    async def reconnect_delayed(self, link: CommsLink):
        backoff = min(5.0 * math.pow(1.1, link.failures), 60.0)
        await trio.sleep(backoff)
        logDebug(f"Attempting to reopen {link}")
        handle = link.open_handle()
        self.state.handle_links[handle] = link

    def create_channel(self, channel_properties: ChannelProperties) -> Optional[CommsChannel]:
        """
        Creates the CommsChannel data structure from RACE ChannelProperties.
        """
        connection_type = ConnectionType(channel_properties.connectionType)
        if self.configuration.is_client and not connection_type.client_ok:
            logDebug(f"Skipping {connection_type} channel {channel_properties.channelGid}"
                     f" because this node is client-like")
            return None
        logDebug(f"Discovered channel {channel_properties.channelGid}")
        channel = CommsChannel(self.race, self.state, channel_properties)
        self._channels[channel.channel_id] = channel
        return channel

    def ensure_channel(self, channel_gid: str) -> Optional[CommsChannel]:
        """
        Returns the channel for channel_gid if present, otherwise creates it.
        """
        channel = self._channels.get(channel_gid)

        if channel:
            return channel

        properties = self.race.getChannelProperties(channel_gid)

        if not properties:
            logWarning(f"Could not find properties for Channel {channel_gid}")
            return None

        return self.create_channel(properties)

    def create_link(self, link_id: str, properties: LinkProperties, handle: Optional[int] = None) -> Optional[CommsLink]:
        """
        Creates the CommsLink data structure from RACE LinkProperties.
        """
        channel = self._channels[properties.channelGid]

        if not channel:
            logWarning(f"No channel {properties.channelGid} discovered yet")
            return None

        link = CommsLink(link_id, channel, properties)

        channel.add_link(link)
        self.links[link_id] = link
        if handle:
            self.state.handle_links[handle] = link

        return link

    def ensure_link(
            self,
            handle: Optional[int] = None,
            link_id: Optional[str] = None,
    ) -> Optional[CommsLink]:
        """Searches for a known link by handle or link_id, creating one if necessary."""
        link: Optional[CommsLink] = self.state.handle_links.get(handle)

        if link:
            return link

        link = self.links.get(link_id)

        if link:
            return link

        logDebug(f"No link found for handle {handle} or link_id {link_id}. Creating a new link.")
        properties = self.race.getLinkProperties(link_id)
        link = self.create_link(link_id, properties, handle=handle)

        return link

    # --------------
    # RACE Callbacks
    # --------------

    def processEncPkg(self, _handle: int, pkg: EncPkg, conn_ids: List[str]) -> int:
        links = [self.connection_links.get(conn_id) for conn_id in conn_ids if conn_id in self.connection_links][:1]
        link = links and links[0]
        context = SpanContext(pkg.getTraceId(), pkg.getSpanId(), None, SAMPLED_FLAG)

        self.state.replay.log_receive(links, bytes(pkg.getCipherText()), pkg.getTraceId())

        try:
            data = self.state.checksum.package_data(pkg)
            message = PrismMessage.decode(data)
            if self.configuration.transport_ignore_old and \
                    message.transport_timestamp is not None and \
                    message.transport_timestamp < self.start_timestamp:
                logWarning("Received message from before startup, discarding")
                return PLUGIN_OK
            prism_package = Package(message, context, datetime.utcnow(), link)
            link.last_receive = datetime.utcnow()
            self.incoming_package_queue.put(prism_package)
        except CorruptPackageError:
            logError(f"Corrupt package (traceID={pkg.getTraceId()}) from {link}")
            return PLUGIN_TEMP_ERROR
        except Exception as e:
            logError(f"Error decoding prism message (traceID={pkg.getTraceId()}): {e}")
            return PLUGIN_TEMP_ERROR

        return PLUGIN_OK

    def onConnectionStatusChanged(
            self, handle: Optional[int], conn_id: str, status: int, link_id: str, _properties: LinkProperties
    ):
        link = self.ensure_link(handle=handle, link_id=link_id)

        if not link:
            logWarning(f"Could not find or create link for {conn_id}")
            return PLUGIN_TEMP_ERROR

        link.connection_status = ConnectionStatus(status)

        if status == CONNECTION_OPEN:
            logDebug(f"Connection {conn_id} opened on {link}")
            with trace_context(None, "connection-open",
                               linkType=link.link_type, link_id=link.link_id,
                               personas=", ".join(link.endpoints), connectionType=link.channel.connection_type):
                pass
            link.connection_id = conn_id
            self.connection_links[conn_id] = link
            self.state.handle_links.pop(handle, None)
            # self.check_finished_startup(handle)
        elif status == CONNECTION_CLOSED:
            logDebug(f"Connection closed on {link}")
            with trace_context(None, "connection-closed",
                               linkType=link.link_type, link_id=link.link_id,
                               personas=", ".join(link.endpoints), connectionType=link.channel.connection_type):
                pass
            if link.manually_closed:
                return PLUGIN_OK

            link.failures += 1
            link.connection_id = None
            self.connection_links.pop(conn_id, None)
            self.dead_link_queue.put(link)
        elif status == CONNECTION_INVALID:
            logWarning(f"Connection {conn_id} invalid")
        else:
            logWarning(f"{link.connection_id} reported status {link.connection_status}")

        return PLUGIN_OK

    def onPackageStatusChanged(self, handle, status):
        if status == PACKAGE_SENT or status == PACKAGE_RECEIVED:
            self.state.successful_packages.add(handle)
        elif (
            status == PACKAGE_FAILED_GENERIC
            or status == PACKAGE_FAILED_NETWORK_ERROR
            or status == PACKAGE_FAILED_TIMEOUT
        ):
            self.state.failed_packages.add(handle)
            logWarning(f"Package {handle} failed.")
        elif status == PACKAGE_INVALID:
            logWarning(f"Package {handle} invalid.")

        return PLUGIN_OK

    def onLinkPropertiesChanged(self, link_id: str, properties: LinkProperties) -> int:
        link = self.ensure_link(None, link_id)

        if not link:
            logWarning(f"Could not find or create Link {link_id}")
            return PLUGIN_TEMP_ERROR

        link.update_properties(properties)
        logDebug(f"Link properties changed for {link}")
        return PLUGIN_OK

    def onLinkStatusChanged(self, handle: int, link_id: str, status: int, _properties: LinkProperties) -> int:
        status = LinkStatus(status)
        logDebug(f"Link status now {status} for {link_id}")
        link = self.ensure_link(handle, link_id)

        if not link:
            logWarning(f"Could not find or create Link {link_id}")
            return PLUGIN_TEMP_ERROR

        link.link_status = status
        return PLUGIN_OK

    def onChannelStatusChanged(self, _handle: int, channel_gid: str, status, _properties: ChannelProperties) -> int:
        channel = self.ensure_channel(channel_gid)
        if not channel:
            logWarning(f"Could not find or create Channel {channel_gid}")
            return PLUGIN_TEMP_ERROR

        channel.status = ChannelStatus(status)

        return PLUGIN_OK
