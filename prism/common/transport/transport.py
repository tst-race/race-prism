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
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set, cast

import structlog
import trio
from jaeger_client import SpanContext

from prism.common.message import PrismMessage, LinkAddress
from .enums import *
from ..config import configuration
from ..constant import TIMEOUT_MS_MAX
from ..epoch.genesis import LinkProfile
from ..tracing import trace_context


DATE_MIN = datetime.utcfromtimestamp(0)


@dataclass
class Package:
    """Represents a received package, so that the receiver gets information
    about the source of the package, in case that is relevant to them."""
    message: PrismMessage
    context: SpanContext
    timestamp: datetime = field(default_factory=datetime.utcnow)
    link: Link = field(default=None)

    def __repr__(self):
        if self.link:
            return f"Package(link={self.link.link_id})"
        else:
            return f"Package(local)"


class Channel:
    status: ChannelStatus
    link_direction: LinkDirection
    transmission_type: TransmissionType
    connection_type: ConnectionType
    reliable: bool
    mtu: int
    bandwidth_bps: int
    latency_ms: int
    loss: float
    tags: Set[str]

    def __init__(self, channel_id: str):
        self.channel_id = channel_id
        tags = configuration.get(f"channel_{channel_id}_tags", None)
        if tags:
            self.tags = set(tags.split(","))
        else:
            self.tags = set()

    def __repr__(self) -> str:
        attrs = ["tags", "status", "queue_size", "mtu", "link_direction", "transmission_type", "connection_type",
                 "reliable", "bandwidth_bps", "latency_ms", "loss"]
        attr_str = "|".join([f"{a}: {getattr(self, a)}" for a in attrs if hasattr(self, a)])
        return f"Channel({self.channel_id}: [{attr_str}]"

    @property
    def links(self) -> List[Link]:
        return []

    async def create_link(self, endpoints: List[str]) -> Optional[Link]:
        pass

    async def load_link(self, link_address: str, endpoints: List[str], link_type: Optional[LinkType], role: Optional[str]) -> Optional[Link]:
        pass


class Link:
    channel: Channel

    link_address: str

    def __init__(self, link_id: str):
        self.link_id = link_id
        self.create_time = datetime.utcnow()
        self.last_send: datetime = DATE_MIN
        self.last_receive: datetime = DATE_MIN
        self.references = []
        self.role = "unknown"
        self.pending_sends = 0

        # meaningful default values for expected attributes
        self.connection_status: ConnectionStatus = ConnectionStatus.CLOSED
        self.link_status: LinkStatus = LinkStatus.UNDEF
        self.link_type: Optional[LinkType] = None
        self.endpoints: List[str] = []

    def __repr__(self) -> str:
        return f"Link({self.link_id}, {self.endpoints}, " \
               f"{self.link_type}, {self.connection_status}, {self.link_status}, " \
               f"{len(self.references)} refs, {self.pending_sends} pending sends)"

    def can_reach(self, address: str) -> bool:
        return address in self.endpoints or address == "*"

    @property
    def can_send(self) -> bool:
        return self.active and self.link_type.can_send

    @property
    def active(self) -> bool:
        return self.connection_status in [ConnectionStatus.OPEN, ConnectionStatus.AVAILABLE]

    @property
    def disposable(self):
        reaper_delay = timedelta(seconds=configuration.transport_reaper_delay_sec)
        quiet = (datetime.utcnow() - self.last_send) > reaper_delay
        not_newly_created = (datetime.utcnow() - self.create_time) > reaper_delay
        return self.active and not self.pending_sends and not self.references and quiet and not_newly_created

    @property
    def address_cbor(self) -> LinkAddress:
        return LinkAddress(channel_id=self.channel.channel_id, link_address=self.link_address)

    @property
    def profile(self) -> LinkProfile:
        return LinkProfile(self.address_cbor, self.link_type.name, self.endpoints, self.role, self.link_type)

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = TIMEOUT_MS_MAX) -> bool:
        pass

    async def open(self):
        pass

    async def close(self):
        pass


class LocalChannel(Channel):
    def __init__(self):
        super().__init__("local")


class LocalLink(Link):
    def __init__(self, transport: Transport):
        super().__init__("local_link")
        self.connection_status = ConnectionStatus.OPEN
        self.link_status = LinkStatus.CREATED
        self.link_type = LinkType.SEND
        self.link_address = "local://"
        self.endpoints = ["local"]
        self.transport = transport
        self.channel = LocalChannel()

    async def send(self, message: PrismMessage, context: SpanContext = None, timeout_ms: int = TIMEOUT_MS_MAX) -> bool:
        self.last_send = datetime.utcnow()
        self.last_receive = datetime.utcnow()
        package = Package(message, context, timestamp=datetime.utcnow(), link=self)
        await self.transport.submit_to_hooks(package)
        return True


class MessageHook:
    """A hook allows a task to register to receive specific messages inline rather than having them
    dispatched through the main message queue. Tasks should subclass MessageHook and override the
    match predicate."""
    _in: trio.MemorySendChannel
    _out: trio.MemoryReceiveChannel

    def __init__(self):
        self._in, self._out = trio.open_memory_channel(math.inf)  # unbounded so that put() doesn't block

    @property
    def in_channel(self):
        return self._in

    def dispose(self):
        """Cleans up the memory channels when the hook is unregistered."""
        self._in.close()
        self._out.close()

    # noinspection PyUnusedLocal
    def match(self, package: Package) -> bool:
        return False

    async def put(self, package: Package):
        await self._in.send(package)

    async def receive_pkg(self) -> Package:
        return cast(Package, await self._out.receive())


# One object of class Transport will be provided to the server on initialization
# It will have channels preconfigured, and may or may not have links already running
class Transport:
    hooks: List[MessageHook]
    message_pool: Dict[str, Package]
    local_address: str

    def __init__(self, config):
        self.configuration = config
        self.hooks = []
        self.message_pool = {}
        self.local_address = config.get('name', None)
        self._logger = structlog.getLogger(__name__)
        self.local_link = LocalLink(self)

    @property
    def overhead_bytes(self) -> int:
        return 0

    @property
    def channels(self) -> List[Channel]:
        return []

    def configure(self, **kwargs):
        pass

    def links_for_address(self, address: str) -> List[Link]:
        return [
            link for channel in self.channels for link in channel.links
            if link.can_send and link.can_reach(address)
        ]

    async def register_hook(self, hook: MessageHook):
        # check new hook for pending messages first
        for pid in list(self.message_pool.keys()):
            package = self.message_pool.get(pid)
            if not package:
                continue

            if hook.match(package):
                await hook.put(package)
                self.message_pool.pop(pid, None)

        self.hooks.append(hook)

    async def _hook_task(self):
        self._logger.debug("Starting hook task")
        while True:
            now = datetime.utcnow()
            drop_threshold = timedelta(seconds=self.configuration.dt_hold_package_sec)
            for pid in list(self.message_pool.keys()):
                package = self.message_pool.get(pid)
                if not package:
                    continue

                if (now - package.timestamp >= drop_threshold) or await self._check_hooks(package):
                    self.message_pool.pop(pid, None)

            await trio.sleep(0.1)

    def remove_hook(self, hook: MessageHook):
        if hook in self.hooks:
            self.hooks.remove(hook)
        hook.dispose()

    async def submit_to_hooks(self, package: Package):
        """Submit incoming package to all registered hooks.  If any of the hooks matches, consumes the package then
        stop.  Otherwise, if never matched, put the package in memory channel for later re-delivery to new hooks."""
        if not await self._check_hooks(package):
            self.message_pool[package.message.hexdigest()] = package

    async def _check_hooks(self, package: Package) -> bool:
        """Check a package with each hook, send it to the ones it matches, and returns whether there was a match."""
        matched = False
        for hook in self.hooks:
            if hook.match(package):
                await hook.put(package)
                matched = True
        return matched

    async def send_to_address(
            self,
            address: LinkAddress,
            message: PrismMessage,
            context: SpanContext = None,
            endpoint: Optional[str] = None,
            timeout_ms: int = TIMEOUT_MS_MAX,
    ) -> bool:
        with trace_context(self._logger, "send-to-address", context, address=address, timeout_ms=timeout_ms) as scope:
            link = await self.load_address(address, [endpoint or "send-to-address"], link_type=LinkType.SEND)

            if not link:
                return False
            try:
                return await link.send(message, scope.context, timeout_ms)
            finally:
                await link.close()

    async def load_address(
            self,
            address: LinkAddress,
            endpoints: List[str],
            link_type: Optional[LinkType] = None,
            role: str = "loader",
    ) -> Optional[Link]:
        channels = [channel for channel in self.channels if channel.channel_id == address.channel_id]
        if not channels:
            self._logger.error(f"Could not load address (channel ID not found): {address.channel_id}")
            return None

        if not channels[0].status.usable:
            self._logger.error(f"Channel {channels[0].channel_id} not available yet")
            return None

        return await channels[0].load_link(address.link_address, endpoints, link_type, role)

    async def load_profile(self, profile: LinkProfile) -> Optional[Link]:
        link = await self.load_address(profile.address, profile.personas, profile.link_type, profile.role)
        if link:
            profile.loaded = True
        return link

    async def run(self):
        """Runs any background tasks that the transport needs to operate, such as polling whiteboards.
        Passes received messages to self.submit_to_hooks()"""
        await self._hook_task()

    def debug_dump(self, logger):
        for channel in self.channels:
            logger.debug(f"{channel}")
            for link in channel.links:
                logger.debug(f"  {link}")
                logger.debug(f"    {link.link_address}")
            logger.debug("\n")
