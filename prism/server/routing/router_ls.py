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
import os
import time
from dataclasses import dataclass, field
from datetime import timedelta, datetime
from typing import Optional, Union, Set, cast, List

import trio
from jaeger_client import SpanContext

from prism.common.message import PrismMessage, TypeEnum, NeighborInfoMap, LinkAddress, HalfKeyMap, create_HKM
from .flood_db import FloodDB
from .neighborhood import Neighborhood, Neighbor
from .network import LinkStateNetwork
from .router import Router
from ..CS2.ark_store import ArkStore
from ...common.config import configuration
from ...common.constant import TIMEOUT_MS_MAX
from ...common.crypto.halfkey import PrivateKey, PublicKey
from ...common.crypto.server_message import encrypt, decrypt
from ...common.crypto.util import make_nonce
from ...common.deduplicate import MessageDeduplicator
from ...common.epoch.genesis import LinkProfile
from ...common.logging import get_logger
from ...common.message_utils import encrypt_message
from ...common.state import StateStore
from ...common.tracing import trace_context
from ...common.transport.enums import ConnectionType, LinkDirection
from ...common.transport.epoch_transport import EpochTransport
from ...common.transport.hooks import MessageTypeHook
from ...common.transport.transport import Link, MessageHook, Package
from ...common.util import frequency_limit, frequency_limit_reset, frequency_limit_trigger


class DelegateAckHook(MessageHook):
    def __init__(self, request_id: bytes):
        super().__init__()
        self.request_id = request_id

    def match(self, package: Package) -> bool:
        return package.message.msg_type == TypeEnum.LSP_FWD_ADDR_ACK and package.message.nonce == self.request_id


@dataclass
class Envelope:
    message: PrismMessage
    context: Optional[SpanContext]
    target: Union[str, bytes, LinkAddress]
    timeout_ms: Union[int, float] = field(default=0)
    sent: trio.Event = field(default_factory=trio.Event)
    send_time: datetime = field(default_factory=datetime.utcnow)
    sent_to: Set[bytes] = field(default_factory=set)
    label: Optional[str] = field(default=None)
    delegate: Optional[bytes] = field(default=None)
    delegate_key: Optional[PublicKey] = field(default=None)

    def __str__(self):
        if isinstance(self.target, bytes):
            target = self.target.hex()
        else:
            target = str(self.target)

        return f"Envelope({target}, {self.message.msg_type})"

    @property
    def expiration(self):
        if self.timeout_ms:
            return self.send_time + timedelta(milliseconds=self.timeout_ms)
        else:
            return datetime.max


class LinkStateRouter(Router):
    def __init__(
            self,
            name: str,
            state_store: StateStore,
            ark_store: ArkStore,
            private_key: PrivateKey,
            transport: EpochTransport,
            neighborhood: Neighborhood,
            broadcast_tags: Set[str],
            uplink: bool,
    ):
        self.name = name
        self.state_store = state_store
        self.ark_store = ark_store
        self.private_key = private_key
        self.logger = get_logger(__name__, epoch=self.epoch)
        self.transport = transport
        self.neighborhood = neighborhood
        self.network = LinkStateNetwork(self.pseudonym, self.epoch, neighborhood, ark_store)
        self.deduplicator = MessageDeduplicator(configuration)
        self.flood_db = FloodDB()
        self.flood_limiter = trio.CapacityLimiter(configuration.ls_flood_concurrency)
        self.envelope_in, self.envelope_out = trio.open_memory_channel(0)
        self.incoming_links: List[Link] = []
        self.broadcast_links: List[Link] = []
        self.uplink_links: List[Link] = []
        self.broadcast_tags = broadcast_tags or set()
        self.uplink = uplink
        self.floods_triggered = 0

    @property
    def pseudonym(self):
        return self.ark_store.own_pseudonym

    @property
    def epoch(self):
        return self.ark_store.current_epoch

    @property
    def broadcast_addresses(self) -> List[LinkAddress]:
        return [link.address_cbor for link in self.broadcast_links
                if link.channel.link_direction.receiver_loaded]

    @property
    def broadcast_mtu(self):
        mtu = configuration.cs2_arks_max_mtu
        for link in self.broadcast_links:
            if link.channel.mtu is not None and link.channel.mtu > 0:
                mtu = min(mtu, link.channel.mtu)
        return mtu - self.transport.overhead_bytes

    async def send(
            self,
            address: Union[str, bytes, LinkAddress],
            message: PrismMessage,
            context: Optional[SpanContext],
            block: bool = False,
            timeout_ms=TIMEOUT_MS_MAX,
            label: Optional[str] = None,
            delegate: Optional[bytes] = None,
            delegate_key: Optional[PublicKey] = None,
            **kwargs
    ) -> bool:
        if delegate == self.pseudonym:
            delegate = None

        envelope = Envelope(
            message=message,
            context=context,
            target=address,
            timeout_ms=timeout_ms,
            label=label,
            delegate=delegate,
            delegate_key=delegate_key,
        )

        await self.envelope_in.send(envelope)
        if block:
            with trio.move_on_after(timeout_ms / 1000.0):
                await envelope.sent.wait()
            if not envelope.sent.is_set():
                if isinstance(address, bytes):
                    address = address.hex()[:8]
                self.logger.warn(f"Send {message.msg_type} to {address} timed out after {timeout_ms}ms")
            return envelope.sent.is_set()

        return True

    async def flood(
            self,
            message: PrismMessage,
            context: Optional[SpanContext],
            hops=0,
            **kwargs
    ):
        flood_msg = PrismMessage(
            msg_type=TypeEnum.LSP_FLOOD,
            hop_count=0,
            nonce=os.urandom(12),
            originator=self.pseudonym,
            micro_timestamp=int(time.time() * 1e6),
            ttl=configuration.ls_time_to_live,
            sub_msg=message,
        )
        envelope = Envelope(
            message=flood_msg,
            context=context,
            target="*flood",
        )
        await self.transport.local_link.send(message, context)
        await self.envelope_in.send(envelope)
        self.floods_triggered += 1

    async def broadcast(
            self,
            message: PrismMessage,
            context: Optional[SpanContext],
            block: bool = False,
            timeout_ms=TIMEOUT_MS_MAX,
            **kwargs
    ) -> bool:
        if not self.broadcast_links:
            return False

        envelope = Envelope(
            message=message,
            context=context,
            target="*broadcast",
        )
        await self.envelope_in.send(envelope)

        if block:
            with trio.move_on_after(timeout_ms / 1000.0):
                await envelope.sent.wait()
            return envelope.sent.is_set()

        return True

    async def add_broadcast_client(self, name: str, address: LinkAddress):
        link = await self.transport.load_address(address, [f"${name}-broadcast"])
        if not link:
            self.logger.warn(f"Failed to load link address {address}")
            return
        self.broadcast_links.append(link)

    async def handle_forward(self, message: PrismMessage, context: SpanContext):
        if message.pseudonym == self.pseudonym:
            await self.transport.local_link.send(message.sub_msg, context)
            return

        envelope = Envelope(
            message=cast(PrismMessage, message.sub_msg),
            context=context,
            target=message.pseudonym,
            sent_to={message.sender}
        )
        await self.envelope_in.send(envelope)

    async def handle_delegate(self, message: PrismMessage, context: SpanContext):
        decrypted = decrypt(message, self.private_key)
        if not isinstance(decrypted, PrismMessage):
            self.logger.warn(f"Could not decrypt FWD ADDR request: {message}")
            return
        with trace_context(self.logger, "delegate-fwd", context) as scope:
            scope.debug(f"Received delegate request {decrypted} from {decrypted.originator.hex()[:6]}")
            if await self.send(
                    decrypted.link_addresses[0],
                    cast(PrismMessage, decrypted.sub_msg),
                    scope.context,
                    block=True
            ):
                ack = PrismMessage(msg_type=TypeEnum.LSP_FWD_ADDR_ACK, nonce=decrypted.nonce)
                await self.send(decrypted.originator, ack, scope.context)

    async def handle_flood(self, message: PrismMessage, context: SpanContext):
        message = validate_ttl(message)
        if not message:
            return

        if not self.flood_db.update(message.nonce, message.hop_count):
            return

        await self.transport.local_link.send(message.sub_msg)

        if message.hop_count > configuration.ls_hops_max:
            return

        flood_msg = message.clone(
            hop_count=message.hop_count + 1,
        )
        envelope = Envelope(
            message=flood_msg,
            context=context,
            target="*flood",
            sent_to={message.sender},
        )
        await self.envelope_in.send(envelope)

    async def handle_lsp(self, message: PrismMessage, _context: SpanContext):
        validated_lsp = validate_ttl(message)
        if validated_lsp:
            if self.network.update(validated_lsp):
                if message.sub_msg:
                    self.ark_store.record(cast(PrismMessage, message.sub_msg))

    def handle_tags(self, source: Optional[Neighbor], message: PrismMessage, _context: SpanContext):
        """
        LSP messages may contain additonal information piggybacked onto the normal contents,
        such as a list of prior messages to ACK, and the rough state of the current LSP database
        """
        # remove ack'd messages from pools
        if message.ls_db_size and source:
            source.ls_db_size = message.ls_db_size

    def tag_for(self, _destination: Neighbor, message: PrismMessage) -> PrismMessage:
        # TODO - Tag messages with ACK batches for neighbors
        return message.clone(
            sender=self.pseudonym,
            ls_db_size=len(self.network),
        )

    async def send_task(self, envelope: Envelope):
        if isinstance(envelope.target, LinkAddress):
            if envelope.delegate:
                self.logger.debug("Handling delegated envelope")
                await self.send_delegate_task(envelope)
            else:
                await self.send_address_task(envelope)
        elif envelope.target == "*flood":
            self.flood_limiter.total_tokens = configuration.ls_flood_concurrency
            async with self.flood_limiter:
                await self.send_flood_task(envelope)
        elif envelope.target == "*broadcast":
            await self.send_broadcast_task(envelope)
        else:
            await self.send_target_task(envelope)

    async def send_address_task(self, envelope: Envelope):
        result = await self.transport.send_to_address(
            envelope.target,
            envelope.message,
            envelope.context,
            timeout_ms=envelope.timeout_ms
        )
        if result:
            envelope.sent.set()

    async def flood_send_neighbor(self, target: bytes, envelope: Envelope, now_sending: Set[bytes]):
        neighbor = self.neighborhood[target]
        neighbor_msg = self.tag_for(neighbor, envelope.message)
        if await neighbor.send(neighbor_msg, envelope.context):
            envelope.sent_to.add(target)
        now_sending.remove(target)

    async def send_flood_task(self, envelope: Envelope):
        time_start = datetime.utcnow()
        flood_timeout = timedelta(seconds=configuration.ls_flood_timeout_sec)
        to_send = self.neighborhood.neighbors.keys() - envelope.sent_to
        now_sending = set()

        async with trio.open_nursery() as nursery:
            while to_send and datetime.utcnow() < time_start + flood_timeout:
                for target in to_send:
                    if target in now_sending:
                        continue
                    now_sending.add(target)
                    nursery.start_soon(self.flood_send_neighbor, target, envelope, now_sending)

                to_send = self.neighborhood.neighbors.keys() - envelope.sent_to - self.neighborhood.dead_neighbors
                await trio.sleep(configuration.ls_flood_sleep)
                flood_timeout = timedelta(seconds=configuration.ls_flood_timeout_sec)

            nursery.cancel_scope.cancel()

        envelope.sent.set()

    async def send_broadcast_task(self, envelope: Envelope):
        tagged_message = envelope.message.clone(epoch=self.epoch)

        for link in self.broadcast_links:
            await link.send(tagged_message, envelope.context)

        envelope.sent.set()

    async def send_target_task(self, envelope: Envelope):
        fwd_msg = PrismMessage(
            msg_type=TypeEnum.LSP_FWD,
            pseudonym=envelope.target,
            sub_msg=envelope.message,
        )
        while True:
            next_hop = self.network.hop(envelope.target)
            neighbor = self.neighborhood[next_hop]
            if not neighbor:
                await trio.sleep(1.0)
                continue

            neighbor_msg = self.tag_for(neighbor, fwd_msg)
            send_context = envelope.context

            if neighbor.pseudonym != envelope.target:
                with trace_context(self.logger, "lsp-fwd", envelope.context,
                                   destination=envelope.target.hex(),
                                   next_hop=neighbor.pseudonym.hex()) as scope:
                    send_context = scope.context

            if await neighbor.send(neighbor_msg, send_context):
                envelope.sent.set()
                return

            await trio.sleep(0.5)

    async def send_delegate_task(self, envelope: Envelope):
        request_id = make_nonce()
        fwd_addr_msg = PrismMessage(
            msg_type=TypeEnum.LSP_FWD_ADDR,
            link_addresses=[envelope.target],
            originator=self.pseudonym,
            sub_msg=envelope.message,
            nonce=request_id,
        )
        delegate_hex = envelope.delegate.hex()[:6]
        encrypted = encrypt_message(
            None,
            fwd_addr_msg,
            message_type=TypeEnum.ENC_LSP_FWD_ADDR,
            public_key=envelope.delegate_key
        )

        with trace_context(self.logger, "delegate-fwd-request", envelope.context) as scope:
            await self.send(
                envelope.delegate,
                encrypted,
                scope.context,
                block=True,
            )
            scope.debug(f"Sent FWD request to {delegate_hex}")

            ack_hook = DelegateAckHook(request_id)
            try:
                await self.transport.register_hook(ack_hook)
                with trio.move_on_after(envelope.timeout_ms / 1000.0):
                    await ack_hook.receive_pkg()
                    scope.debug(f"Received ACK for FWD request from {delegate_hex}")
                    envelope.sent.set()
            finally:
                self.transport.remove_hook(ack_hook)

    async def send_lsp(self):
        message = PrismMessage(
            msg_type=TypeEnum.LSP,
            name=self.name,
            pseudonym=self.pseudonym,
            micro_timestamp=int(datetime.utcnow().timestamp() * 1e6),
            ttl=configuration.ls_time_to_live,
            neighbors=[NeighborInfoMap(pseudonym=n.pseudonym, cost=1)
                       for n in self.neighborhood if n.online],
            sub_msg=self.ark_store.own_ark,
        )
        await self.flood(message, None, hops=configuration.ls_hops_max)

    def trigger_lsp_flood(self):
        category = f"lsp-flood-{self.epoch}"
        frequency_limit_trigger(category)

    async def lsp_loop(self):
        # This function uses two separate frequency limiters: one for the regular update cadence, and one to "debounce"
        # neighbor and ARK-related updates so that events such as several neighbors coming online in rapid sequence
        # don't result in a massive spike in flood traffic.
        category = f"lsp-flood-{self.epoch}"
        debounce_category = f"lsp-flood-{self.epoch}-debounce"
        # track how many frequency-limited refreshes we've sent
        # so we can speed up after the Nth one
        sequence_no = 1

        # An initial delay helps debounce the flurry of activity at the start of every epoch
        if configuration.ls_initial_delay_sec:
            await trio.sleep(configuration.ls_initial_delay_sec)

        last_ark = self.ark_store.own_ark
        last_neighbors = [neighbor.pseudonym for neighbor in self.neighborhood if neighbor.online]

        while True:
            # Reload frequency limits from config at the start of each loop in case they've changed
            debounce_interval = timedelta(seconds=configuration.ls_update_debounce_sec)
            if sequence_no > configuration.ls_early_refresh_count:
                interval = timedelta(seconds=configuration.ls_time_to_live * configuration.ls_own_refresh)
            else:
                interval = timedelta(seconds=configuration.ls_time_to_live * configuration.ls_early_refresh_factor)

            if frequency_limit(category, limit=interval):
                await self.send_lsp()
                sequence_no += 1
                continue

            new_ark = self.ark_store.own_ark
            new_neighbors = [neighbor.pseudonym for neighbor in self.neighborhood if neighbor.online]

            update_reason = ""
            if last_ark != new_ark:
                update_reason = "Own ARK changed"
            elif last_neighbors != new_neighbors:
                update_reason = "Neighbor status changed"

            if update_reason:
                if not frequency_limit(debounce_category, limit=debounce_interval):
                    await trio.sleep(1.0)
                    continue
                self.logger.debug(f"{update_reason}, re-flooding LSP.")
                await self.send_lsp()
                # Since we've updated our LSP, the regular timer can be kicked back down the road by its full duration
                frequency_limit_reset(category)

            last_ark = new_ark
            last_neighbors = new_neighbors

            await trio.sleep(1.0)

    async def receive_loop(self, nursery: trio.Nursery):
        hook = MessageTypeHook(
            None,
            TypeEnum.LSP, TypeEnum.LSP_FWD, TypeEnum.LSP_FLOOD, TypeEnum.ENC_LSP_FWD_ADDR,
            TypeEnum.LSP_HELLO, TypeEnum.LSP_DATABASE_REQUEST, TypeEnum.LSP_DATABASE_RESPONSE
        )
        await self.transport.register_hook(hook)

        while True:
            pkg = await hook.receive_pkg()
            message = pkg.message
            source = self.neighborhood[message.sender]

            if source:
                source.last_received = datetime.utcnow()
            elif message.sender == self.pseudonym:
                pass
            elif message.msg_type not in [TypeEnum.LSP, TypeEnum.ENC_LSP_FWD_ADDR]:
                self.logger.warn(f"Unknown source ({message.sender.hex()} for message " + str(message.msg_type))

            # Spin off into async?
            self.handle_tags(source, message, pkg.context)

            if message.msg_type == TypeEnum.LSP:
                nursery.start_soon(self.handle_lsp, message, pkg.context)
            elif message.msg_type == TypeEnum.LSP_FWD:
                nursery.start_soon(self.handle_forward, message, pkg.context)
            elif message.msg_type == TypeEnum.ENC_LSP_FWD_ADDR:
                nursery.start_soon(self.handle_delegate, message, pkg.context)
            elif message.msg_type == TypeEnum.LSP_FLOOD:
                nursery.start_soon(self.handle_flood, message, pkg.context)
            elif message.msg_type == TypeEnum.LSP_HELLO:
                pass
            elif message.msg_type == TypeEnum.LSP_DATABASE_REQUEST:
                if not source:
                    self.logger.warn(f"Received LS DB Request from unknown neighbor {message.sender}")
                else:
                    nursery.start_soon(self.handle_db_request, message, pkg.context)
            elif message.msg_type == TypeEnum.LSP_DATABASE_RESPONSE:
                nursery.start_soon(self.handle_db_response, message, pkg.context)
            else:
                self.logger.warn(f"LSP handler for {message.msg_type} not yet implemented.")

    async def send_loop(self, nursery: trio.Nursery):
        async with self.envelope_out:
            async for envelope in self.envelope_out:
                nursery.start_soon(self.send_task, envelope)

    async def link_request_loop(self):
        hook = MessageTypeHook(
            self.pseudonym,
            TypeEnum.ENCRYPT_LINK_REQUEST,
        )
        await self.transport.register_hook(hook)

        while True:
            pkg = await hook.receive_pkg()
            decrypted = decrypt(pkg.message, self.private_key)
            if not isinstance(decrypted, PrismMessage):
                continue

            self.logger.debug(f"Received link request from {decrypted.name}")

            neighbor = self.neighborhood[decrypted.pseudonym]
            if not neighbor:
                self.logger.debug("Link request not from neighbor, adding")
                self.neighborhood.update(
                    decrypted.name,
                    decrypted.pseudonym,
                    decrypted.half_key.to_key(),
                    decrypted.link_addresses,
                    decrypted.whiteboard_ID
                )
                neighbor = self.neighborhood[decrypted.pseudonym]

            for address in decrypted.link_addresses:
                channel_id = address.channel_id
                if any(l.channel.channel_id == channel_id for l in neighbor.data_links):
                    self.logger.debug(f"Already have link to {neighbor.name} on {channel_id}, skipping")
                    continue

                link = await self.transport.load_address(address, [decrypted.pseudonym.hex()])
                if link:
                    self.logger.debug(f"Created link to {neighbor.name} on {channel_id}")
                    neighbor.data_links.append(link)
                    break

    async def maintenance_loop(self):
        maintained_neighbors = []
        async with trio.open_nursery() as nursery:
            while True:
                for neighbor in self.neighborhood:
                    if neighbor not in maintained_neighbors:
                        nursery.start_soon(self.maintain_neighbor, neighbor)
                        maintained_neighbors.append(neighbor)

                if frequency_limit("router-state-save", timedelta(seconds=configuration.ls_router_save_interval_sec)):
                    self.save_state()

                await trio.sleep(1.0)

    async def maintain_neighbor(self, neighbor: Neighbor):
        while True:
            if not neighbor.online and (datetime.utcnow() - neighbor.last_initiated) > \
                    timedelta(seconds=configuration.ls_neighbor_connect_interval_sec):
                await self.connect(neighbor)
                neighbor.last_initiated = datetime.utcnow()

            db_interval = timedelta(seconds=configuration.ls_request_neighbor_db_interval_sec)
            if neighbor.online and neighbor.ls_db_size > len(self.network) and \
                    (datetime.utcnow() - neighbor.last_requested_db) > db_interval:
                if await self.request_ls_db(neighbor):
                    neighbor.last_requested_db = datetime.utcnow()

            send_interval = timedelta(milliseconds=configuration.ls_hello_timeout_ms)
            # If send links quiet too long, send hello
            for link in neighbor.data_links:
                if not link.can_send:
                    continue
                if datetime.utcnow() - link.last_send > send_interval:
                    await self.say_hello(link)

            await trio.sleep(0.5)

    async def monitor_neighbors(self):
        previous_neighbors = set()
        await trio.sleep(5.0)

        while True:
            active_neighbors = {neighbor.name for neighbor in self.neighborhood if neighbor.online}
            new_neighbors = active_neighbors - previous_neighbors
            dead_neighbors = previous_neighbors - active_neighbors

            for neighbor in new_neighbors:
                with trace_context(self.logger, "neighbor-connected", epoch=self.epoch, persona=neighbor):
                    pass

            for neighbor in dead_neighbors:
                with trace_context(self.logger, "neighbor-disconnected", epoch=self.epoch, persona=neighbor):
                    pass

            previous_neighbors = active_neighbors

            await trio.sleep(5.0)

    def make_link_request(self, neighbor: Neighbor) -> PrismMessage:
        inner_request = PrismMessage(
            TypeEnum.LINK_REQUEST,
            name=self.name,
            pseudonym=self.pseudonym,
            half_key=create_HKM(self.private_key.public_key().cbor()),
            link_addresses=[link.address_cbor for link in self.incoming_links],
            whiteboard_ID=neighbor.tag,
        )

        private_key = neighbor.public_key.generate_private()
        nonce = make_nonce()

        outer_request = PrismMessage(
            TypeEnum.ENCRYPT_LINK_REQUEST,
            pseudonym=neighbor.pseudonym,
            nonce=nonce,
            half_key=HalfKeyMap.from_key(private_key.public_key()),
            ciphertext=encrypt(inner_request, private_key, neighbor.public_key, nonce),
        )

        return outer_request

    async def connect(self, neighbor: Neighbor):
        if not neighbor.control_addresses:
            return

        self.logger.debug(f"Sending connection request to {neighbor}")
        link_request = self.make_link_request(neighbor)
        for address in neighbor.control_addresses:
            self.logger.debug(f"On link {address}")
            await self.send(address, link_request, None)

    async def request_ls_db(self, neighbor: Neighbor):
        with trace_context(self.logger, "request-ls-db") as scope:
            scope.debug(f"Requesting LS DB from neighbor {neighbor.name} ({neighbor.ls_db_size} vs {len(self.network)}")
            message = PrismMessage(
                msg_type=TypeEnum.LSP_DATABASE_REQUEST,
                sender=self.pseudonym,
                epoch=self.epoch,
            )
            return await neighbor.send(message, scope.context)

    async def handle_db_request(self, message: PrismMessage, context: SpanContext):
        neighbor = self.neighborhood[message.sender]
        response = PrismMessage(
            msg_type=TypeEnum.LSP_DATABASE_RESPONSE,
            submessages=list(self.network.database.values()),
            sender=self.pseudonym,
            epoch=self.epoch,
        )
        with trace_context(self.logger, "ls-db-response", context) as scope:
            await neighbor.send(response, scope.context)

    async def handle_db_response(self, message: PrismMessage, context: SpanContext):
        with trace_context(self.logger, "receive-ls-db", context) as scope:
            neighbor = self.neighborhood[message.sender]
            scope.debug(f"Received LS DB of size {len(message.submessages)} from {neighbor.name}")
            for lsp in message.submessages:
                await self.handle_lsp(cast(PrismMessage, lsp), scope.context)

    async def say_hello(self, link: Link):
        message = PrismMessage(
            msg_type=TypeEnum.LSP_HELLO,
            sender=self.pseudonym,
            epoch=self.epoch,
        )
        await link.send(message)

    @property
    def control_channels(self):
        return [channel for channel in self.transport.channels
                if "epoch" in channel.tags]

    @property
    def data_channels(self):
        return [channel for channel in self.transport.channels
                if channel.connection_type == ConnectionType.DIRECT and
                channel.link_direction == LinkDirection.LOADER_TO_CREATOR]

    @property
    def broadcast_channels(self):
        return [channel for channel in self.transport.channels
                if channel.connection_type == ConnectionType.INDIRECT and
                channel.tags.intersection(self.broadcast_tags)]

    @property
    def uplink_channels(self):
        return [channel for channel in self.transport.channels
                if channel.connection_type.client_ok and
                channel.link_direction.sender_loaded and
                "uplink" in channel.tags]

    def online(self, pseudonym: bytes) -> bool:
        neighbor = self.neighborhood[pseudonym]
        if not neighbor:
            return False
        return neighbor.online

    async def run(self):
        if not self.incoming_links:
            for channel in self.data_channels:
                self.incoming_links.append(await channel.create_link([f"{self.epoch}-incoming"]))
        if not self.broadcast_links:
            for channel in self.broadcast_channels:
                self.broadcast_links.append(await channel.create_link([f"{self.epoch}-broadcast"]))
        if self.uplink and not self.uplink_links:
            for channel in self.uplink_channels:
                self.uplink_links.append(await channel.create_link([f"{self.epoch}-uplink"]))

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.lsp_loop)
            nursery.start_soon(self.deduplicator.purge_task)
            nursery.start_soon(self.receive_loop, nursery)
            nursery.start_soon(self.send_loop, nursery)
            nursery.start_soon(self.maintenance_loop)
            nursery.start_soon(self.monitor_neighbors)
            nursery.start_soon(self.link_request_loop)

    def debug_dump(self, logger):
        logger.debug(f"Ongoing floods: {self.flood_limiter.borrowed_tokens}/{self.flood_limiter.total_tokens}")
        logger.debug(f"Queued floods: {self.flood_limiter.statistics().tasks_waiting}")
        logger.debug(f"Originated floods: {self.floods_triggered}")

        logger.debug(f"Router: Incoming links:")
        for link in self.incoming_links:
            logger.debug(f"  {link}")

        if self.uplink:
            logger.debug(f"Router: Uplink channels: {self.uplink_channels}")
            logger.debug(f"Router: Uplinks")
            for link in self.uplink_links:
                logger.debug(f"  {link}")

        logger.debug(f"Router: Broadcast channels: {self.broadcast_channels}")
        logger.debug(f"Router: Broadcast links (tags {self.broadcast_tags}):")
        for link in self.broadcast_links:
            logger.debug(f"  {link}")

        self.network.debug_dump(logger)
        self.neighborhood.debug_dump(logger)

    def save_state(self):
        state = {
            "neighborhood": self.neighborhood.save_data(),
            "incoming_links": [link.profile.to_dict() for link in self.incoming_links],
            "uplink_links": [link.profile.to_dict() for link in self.uplink_links],
            "broadcast_links": [link.profile.to_dict() for link in self.broadcast_links],
        }
        self.state_store.save_state("router-ls", state)

    async def load_state(self):
        state = self.state_store.load_state("router-ls")
        self.logger.debug(f"Loaded router state: {state}")
        if not state:
            self.logger.warning("Could not load router state.")

        incoming_links = [LinkProfile.from_dict(None, p) for p in state["incoming_links"]]
        uplink_links = [LinkProfile.from_dict(None, p) for p in state["uplink_links"]]
        broadcast_links = [LinkProfile.from_dict(None, p) for p in state["broadcast_links"]]
        neighbor_links = self.neighborhood.load_data(state["neighborhood"])

        async def load_link(prof):
            lnk = await self.transport.load_profile(prof)
            if not lnk:
                self.logger.warning(f"Failed to load saved link profile {prof}")
            return lnk

        unloaded = True
        while unloaded:
            unloaded = False

            for profile in incoming_links:
                if profile.loaded:
                    continue

                link = await load_link(profile)
                if link:
                    self.incoming_links.append(link)
                else:
                    unloaded = True

            for profile in uplink_links:
                if profile.loaded:
                    continue

                link = await load_link(profile)
                if link:
                    self.uplink_links.append(link)
                else:
                    unloaded = True

            for profile in broadcast_links:
                if profile.loaded:
                    continue

                link = await load_link(profile)
                if link:
                    self.broadcast_links.append(link)
                else:
                    unloaded = True

            for (neighbor, profile) in neighbor_links:
                if profile.loaded:
                    continue

                link = await load_link(profile)
                if link:
                    self.neighborhood[neighbor].data_links.append(link)
                else:
                    unloaded = True

            await trio.sleep(1.0)


def validate_ttl(message: PrismMessage) -> Optional[PrismMessage]:
    # If the message claims to be from more than 30 seconds in the future, ignore it
    micro_thirty_secs_future = int((datetime.utcnow() + timedelta(seconds=30)).timestamp() * 1e6)
    if message.micro_timestamp > micro_thirty_secs_future:
        return

    # TTL stays in [0; TTL_MAX]
    validated_lsp = message.clone(ttl=max(min(message.ttl, configuration.ls_ttl_max), 0))
    return validated_lsp
