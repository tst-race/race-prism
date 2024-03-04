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
import random
from abc import ABCMeta, abstractmethod
from base64 import b64decode
from contextlib import contextmanager
from datetime import timedelta, datetime, timezone
from queue import Queue, Empty
from typing import List, Optional, Union, Generator, cast

import structlog
import trio
from jaeger_client import SpanContext

from prism.client.dropbox import Dropboxes
from prism.client.message_store import MessageStore
from prism.client.routing import find_route, MessageRoute
from prism.client.send_log import SendLog, SendLogEntry
from prism.client.server_db import ServerDB, ServerRecord
from prism.common.cleartext import ClearText
from prism.common.config import configuration, init_watchdog
from prism.common.config.config import dump_config
from prism.common.crypto.halfkey.ecdh import EllipticCurveDiffieHellman
from prism.common.crypto.ibe import BonehFranklin
from prism.common.crypto.pki import CommonPKI
from prism.common.crypto.server_message import decrypt
from prism.common.crypto.util import make_nonce
from prism.common.crypto.verify import verify_ARK
from prism.common.deduplicate import MessageDeduplicator
from prism.common.epoch import EpochCommand, EpochCommandType
from prism.common.epoch.genesis import GenesisInfo
from prism.common.logging import MONITOR_STATUS
from prism.common.message import PrismMessage, TypeEnum, HalfKeyMap
from prism.common.message_utils import encrypt_user_message, decrypt_user_message, encrypt_message
from prism.common.pseudonym import Pseudonym
from prism.common.state import StateStore
from prism.common.tracing import init_tracer, PrismScope, trace_context
from prism.common.transport.epoch_transport import EpochTransport
from prism.common.transport.maintenance import maintain_incoming_links
from prism.common.transport.transport import Transport, Link, MessageHook, Package
from prism.common.util import frequency_limit, posix_utc_now, report_error, frequency_limit_reset, \
    frequency_limit_trigger


class MessageDelegate(metaclass=ABCMeta):
    @abstractmethod
    def message_received(self, cleartext: ClearText):
        pass


class ClientMessageHook(MessageHook):
    def match(self, package: Package) -> bool:
        return True


class PrismClient:
    def __init__(
            self,
            transport: Transport,
            state_store: StateStore,
            delegate: MessageDelegate = None,
            server_db: Optional[ServerDB] = None,
            genesis_info: Optional[GenesisInfo] = None,
    ):
        self.current_epoch = "genesis"
        self.genesis_info = genesis_info
        self.base_transport = transport
        self.delegate = delegate
        self.state_store = state_store
        self.servers = server_db or ServerDB(state_store=state_store, epoch=self.current_epoch)
        self.dropboxes = Dropboxes(configuration)

        self.config = configuration
        self.watchdog = init_watchdog()
        self.logger = structlog.get_logger("prism.client")
        self.monitor_logger = structlog.get_logger(MONITOR_STATUS)

        init_tracer(self.logger, configuration, service=configuration.name)

        self.ibe = BonehFranklin.load(configuration.name, configuration.private_key, configuration.public_params)
        self.registration_halfkey = None
        self.registration_nonces = {}
        self.registration_keys = {}
        self.pseudonym = Pseudonym.from_address(self.config.name, self.config.pseudonym_salt)
        self.pki = CommonPKI(configuration)

        self.send_log = SendLog(self.servers)
        self.message_store = MessageStore(self.config)
        self.incoming_dedupe = MessageDeduplicator(self.config)
        self.outgoing_dedupe = MessageDeduplicator(self.config)
        self.encrypted_message_queue = []

        self.ark_links = []
        self.dropbox_links: List[Link] = []
        self.connected_emixes: List[ServerRecord] = []
        self.emix_broadcast_links: List[Link] = []
        self.return_links = []
        self.running = True
        self.incoming_epoch: Optional[str] = None
        self.outgoing_epoch: Optional[str] = None
        self.epoch_command_queue: Queue[EpochCommand] = Queue()
        self.current_transport = EpochTransport(self.base_transport, self.current_epoch)
        self.outgoing_transport: Optional[EpochTransport] = None

    def __str__(self) -> str:
        pass

    async def start(self):
        try:
            await self.launch_tasks()
        except:
            import traceback
            with self.trace("fatal-error") as scope:
                scope.error(traceback.format_exc())
            raise

    def epoch_command(self, command: EpochCommand):
        self.epoch_command_queue.put(command)

    async def epoch_command_task(self):
        while True:
            try:
                command = self.epoch_command_queue.get_nowait()

                if command.command_type == EpochCommandType.NEW:
                    self.incoming_epoch = command.epoch_seed
                    self.logger.debug(f"Preparing for incoming epoch {self.incoming_epoch}")
                elif command.command_type == EpochCommandType.NEXT:
                    if self.outgoing_epoch:
                        await self.outgoing_transport.shutdown()

                    self.outgoing_epoch = self.current_epoch
                    self.current_epoch = self.incoming_epoch
                    self.servers.current_epoch = self.incoming_epoch
                    self.outgoing_transport = self.current_transport
                    self.current_transport = EpochTransport(self.base_transport, self.current_epoch)
                    self.incoming_epoch = None
                    self.logger.debug(f"Switched to epoch {self.current_epoch}")

                    self.return_links = [self.current_transport.promote(link) for link in self.return_links]
                    self.ark_links = [self.current_transport.promote(link) for link in self.ark_links]

                    frequency_limit_trigger("link-maintenance-emix")
                elif command.command_type == EpochCommandType.OFF:
                    if self.outgoing_epoch:
                        await self.outgoing_transport.shutdown()
                    self.outgoing_epoch = None
                    self.outgoing_transport = None
                elif command.command_type == EpochCommandType.POLL:
                    for dropbox in self.my_dropboxes:
                        db_rec = self.dropboxes.lookup(dropbox)
                        db_rec.last_polled = datetime.min
                elif command.command_type == EpochCommandType.CONFIG:
                    command.update_config(self.logger)
                elif command.command_type == EpochCommandType.DEBUG:
                    self.debug_dump(self.logger)

            except Empty:
                pass

            await trio.sleep(1.0)

    async def launch_tasks(self):
        with self.trace("client-started") as scope:
            scope.debug("Launching startup tasks")

        if self.genesis_info:
            await self.load_genesis_links(self.genesis_info)

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.send_task)
            nursery.start_soon(self.receive_task)
            nursery.start_soon(self.poll_task)
            nursery.start_soon(self.link_maintenance_task)
            nursery.start_soon(self.monitor_task)
            nursery.start_soon(self.incoming_dedupe.purge_task)
            nursery.start_soon(self.outgoing_dedupe.purge_task)
            nursery.start_soon(self.watchdog.main)
            nursery.start_soon(self.epoch_command_task)

            if not self.ibe.can_decrypt:
                nursery.start_soon(self.bootstrap_task)

            if self.config.client_rest_api:
                from .web.api import run_api
                nursery.start_soon(run_api, self)

    def shutdown(self):
        self.running = False

    async def send_task(self):
        self.logger.debug("Send task launched")

        while True:
            if self.incoming_epoch:
                if frequency_limit("epoch-pause"):
                    self.logger.debug("Pausing sends while epoch transition is ongoing")
                await trio.sleep(1.0)
                continue
            with self.send_log.attempt() as entry:
                if entry:
                    await self.attempt_send(entry)
            await trio.sleep(0.1)

    async def receive_task(self):
        self.logger.debug("Receive task launched")
        hook = ClientMessageHook()
        await self.base_transport.register_hook(hook)

        while True:
            pkg = await hook.receive_pkg()
            self.process_message(pkg.message, pkg.context)

    async def link_maintenance_task(self):
        await trio.sleep(10.0)
        while True:
            await self.maintain_emix_links()
            await self.maintain_dropbox_links()
            await maintain_incoming_links(
                self.logger,
                self.current_transport,
                self.return_links,
                {"downlink"},
                make_nonce().hex(),
            )
            await maintain_incoming_links(
                self.logger,
                self.current_transport,
                self.ark_links,
                {"ark"},
                make_nonce().hex(),
            )
            await trio.sleep(10.0)

    @property
    def current_emixes(self):
        return [e for e in self.connected_emixes if e.epoch == self.current_epoch]

    async def maintain_emix_links(self):
        emix_count = len(self.current_emixes)

        dead_emixes = []
        for emix in self.connected_emixes:
            if datetime.utcnow() - emix.last_broadcast > \
                    timedelta(seconds=self.config.client_emix_disconnect_timeout_sec):
                dead_emixes.append(emix)
        if dead_emixes:
            self.logger.debug(f"Pruning {len(dead_emixes)} non-broadcasting emixes from connection list:")
            for emix in dead_emixes:
                self.logger.debug(f"  {emix}")
                self.connected_emixes.remove(emix)
                self.servers.update_status(emix.pseudonym, emix.pseudonym, datetime.utcnow(), False)
                # Reset the frequency limiter to give emixes declared dead one last chance to send another message
                frequency_limit_reset("link-maintenance-emix")

        if frequency_limit("connected-emixes"):
            self.logger.debug(f"Connected to {emix_count} emixes: {self.current_emixes}")

        interval = timedelta(seconds=self.config.link_maintenance_interval_sec)
        if emix_count < self.config.client_emix_count:
            candidates = self.emix_candidates()
            if candidates and frequency_limit("link-maintenance-emix", interval):
                self.logger.debug(f"Attempting link maintenance because "
                                  f"emix count {emix_count} < desired count {self.config.client_emix_count}")
                self.logger.debug(f"Found candidates: {candidates}")
                await self.connect_to_emix(random.choice(candidates))

        for emix in self.current_emixes:
            for address in emix.ark.broadcast_addresses or []:
                matching_links = [link for link in self.emix_broadcast_links
                                  if link.link_address == address.link_address]
                if not matching_links:
                    self.logger.debug(f"Loading broadcast link address for EMIX {emix.name}")
                    new_link = await self.current_transport.load_address(
                        address,
                        [f"${emix.name}-broadcast"],
                    )
                    if new_link:
                        self.emix_broadcast_links.append(new_link)

    async def maintain_dropbox_links(self):
        for dropbox in self.my_dropboxes:
            for address in dropbox.ark.broadcast_addresses or []:
                matching_links = [link for link in self.dropbox_links if link.link_address == address.link_address]
                if not matching_links:
                    self.logger.debug(f"Loading broadcast link address for DROPBOX {dropbox.name}")
                    new_link = await self.current_transport.load_address(
                        address,
                        [f"${dropbox.name}-broadcast"],
                    )
                    if new_link:
                        self.dropbox_links.append(new_link)

    async def connect_to_emix(self, emix: ServerRecord):
        if not emix.ark.broadcast_addresses:
            if not self.ark_links:
                self.logger.debug(f"No ARK links and no broadcast links. Delaying connection.")
                return

            self.logger.debug(f"Emix {emix} has no broadcast address, sending connection request")
            # TODO - make sure to find an agreeable channel
            ark_link: Link = random.choice(self.ark_links)
            request = PrismMessage(
                msg_type=TypeEnum.LINK_REQUEST,
                link_addresses=[ark_link.address_cbor],
                name="client",
            )
            encrypted_request = encrypt_message(emix, request)

            for address in emix.ark.link_addresses:
                await self.current_transport.send_to_address(address, encrypted_request)
            self.logger.debug(f"Sent EMIX connect request: {request}")

        emix.last_broadcast = datetime.utcnow()
        self.connected_emixes.append(emix)

    def process_message(self, message: PrismMessage, context: SpanContext):
        if not self.incoming_dedupe.is_msg_new(message):
            return

        if message.msg_type == TypeEnum.ARKS:
            self.process_arks(message, context)
        elif message.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY:
            self.process_ark(message, context)
        elif message.msg_type == TypeEnum.NARK:
            self.process_nark(message, context)
        elif message.msg_type == TypeEnum.ENCRYPT_USER_MESSAGE:
            if self.ibe.can_decrypt:
                self.process_encrypted_user_message(message, context)
            else:
                self.logger.debug("Received message but IBE not configured yet. Queueing.")
                self.encrypted_message_queue.append((message, context))
        elif message.msg_type == TypeEnum.ENCRYPT_REGISTRATION_MESSAGE:
            self.process_encrypted_registration_message(message, context)
        elif message.msg_type == TypeEnum.ENCRYPTED_READ_OBLIVIOUS_DROPBOX_RESPONSE:
            self.process_encrypted_mpc_dropbox_response(message, context)

    async def poll_task(self):
        self.logger.debug("Poll task launched")

        while self.running:
            try:
                if self.polling:
                    await self.make_poll_request()
            except Exception as e:
                report_error(self.logger, "poll request", e)

            await trio.sleep(1.0)

    def monitor_data(self, epoch: str) -> dict:
        reachable_servers = self.servers.reachable_servers
        reachable_count = len(reachable_servers)

        if not reachable_servers:
            avg_expiry = 0.0
        else:
            now = datetime.utcnow()
            avg_expiry = sum((s.expiration - now).total_seconds() for s in reachable_servers) / reachable_count

        expired_servers = [server for server in self.servers.expired_servers]

        return {
            "epoch": epoch,
            "backlog": len(self.send_log),
            "valid_server_count": reachable_count,
            "expired_server_count": len(expired_servers),
            "avg_time_to_expiry": avg_expiry,
            "polling": self.polling and epoch == self.current_epoch,
            "monitor_ts": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "monitor_interval": self.config.log_monitor_interval,
        }

    async def monitor_task(self):
        if not self.config.log_dir:
            return

        self.logger.debug("Monitor task launched")
        while self.running:
            try:
                interval = timedelta(seconds=self.config.log_monitor_interval)
                if frequency_limit("monitor-log", interval):
                    monitor_epochs = filter(None, [self.current_epoch, self.incoming_epoch, self.outgoing_epoch])

                    for epoch in monitor_epochs:
                        data = self.monitor_data(epoch)
                        self.monitor_logger.info(f"still alive", **data)
                        with self.trace("monitor-client", **data):
                            pass
            except Exception as e:
                report_error(self.logger, "monitor logging", e)
            finally:
                await trio.sleep(0.1)

    async def bootstrap_task(self):
        self.load_bootstrap_info()

        self.registration_halfkey = EllipticCurveDiffieHellman().generate_private()

        registration_servers = [f"{self.config.ibe_committee_name}-{i}" for i in range(1, self.config.ibe_shards + 1)]
        self.registration_nonces = {s: make_nonce() for s in registration_servers}
        self.registration_keys = {}

        while not self.ibe.can_decrypt:
            interval = timedelta(seconds=self.config.bootstrap_request_interval_sec)
            for server in registration_servers:
                if server not in self.registration_keys and frequency_limit(f"bootstrap-request-{server}", interval):
                    await self.send_bootstrap_request(server, self.registration_nonces[server])

            await trio.sleep(0.1)

        for message, context in self.encrypted_message_queue:
            self.process_encrypted_user_message(message, context)
            await trio.sleep(0.1)

    def load_bootstrap_info(self):
        if self.config.get("bootstrap_arks"):
            self.current_epoch = self.config.get("bootstrap_epoch", "genesis")
            self.current_transport = EpochTransport(self.base_transport, self.current_epoch)
            self.servers.current_epoch = self.current_epoch
            arks = [PrismMessage.decode(b64decode(b64ark)) for b64ark in self.config.bootstrap_arks]
            for ark in arks:
                self.servers.record(ark)
        else:
            raise AttributeError("Could not find bootstrap ARKs")

    async def send_bootstrap_request(self, server_name: str, nonce: bytes):
        inner_request = PrismMessage(
            msg_type=TypeEnum.CLIENT_REGISTRATION_REQUEST,
            name=self.config.name,
            nonce=nonce,
            half_key=HalfKeyMap.from_key(self.registration_halfkey.public_key()),
        )

        with self.trace("bootstrap-request-ibe-key", me=self.config.name, committee_member=server_name) as scope:
            clear = ClearText(
                sender=self.config.name,
                receiver=server_name,
                message_bytes=inner_request.encode(),
                context=scope.context,
            )

            self.process_clear_text(clear)

    @property
    def polling(self) -> bool:
        return self.config.polling and self.can_poll()

    @property
    def ready(self) -> bool:
        return self.ibe.can_decrypt and self.polling

    def can_poll(self) -> bool:
        if self.config.dynamic_links and not (self.return_links or self.dropbox_links):
            if frequency_limit("return-links"):
                self.logger.debug("CAN-POLL: Return links not available yet")
            return False

        first_hops = self.first_hops()

        if not first_hops:
            if frequency_limit("first-hops"):
                self.logger.debug(f"CAN-POLL: No first hops found in {self.servers}")
            return False

        for dropbox in self.my_dropboxes:
            if find_route(self.servers, self.current_transport, dropbox, self.config.onion_layers, []):
                return True

        if frequency_limit("no-dropboxes"):
            self.logger.debug(f"CAN-POLL: No routes found to dropboxes in {self.my_dropboxes}")

        return False

    def process_clear_text(self, clear: ClearText):
        if len(clear) > self.config.max_plaintext_size:
            self.logger.error(f"Message size greater than maximum ({len(clear)} > {self.config.max_plaintext_size})")
            return

        with self.trace("send-message",
                        clear.context,
                        sender=self.config.name,
                        recipient=clear.receiver,
                        message=clear.message) as scope:
            clear.context = scope.context
            scope.debug(f"process_clear_text ({clear.trace_id}): {clear}")
            self.send_log.add(clear)
            self.message_store.record(clear)

    def emix_candidates(self) -> List[ServerRecord]:
        return [s for s in self.first_hops() if s not in self.current_emixes]

    def first_hops(self) -> List[ServerRecord]:
        return [s for s in self.servers.reachable_emixes if s.ark.link_addresses]

    async def attempt_send(self, entry: SendLogEntry):
        message = entry.message
        target_pseudonym = Pseudonym.from_address(message.receiver, self.config.pseudonym_salt)

        try:
            dropboxes = self.servers.dropboxes_for_recipient(
                target_pseudonym,
                self.config.dropbox_count,
                self.config.dropboxes_per_client,
                self.current_epoch,
            )
            targets = list(entry.targets(dropboxes))
            random.shuffle(targets)

            for dropbox in targets[0:entry.sends_remaining]:
                route = find_route(
                    self.servers,
                    self.current_transport,
                    dropbox,
                    self.config.onion_layers,
                    entry.routes_sent,
                )

                if not route:
                    continue

                with self.trace("route-message", message.context) as scope:
                    scope.debug(f"Message route: {route}")
                    wrapped = self.wrap_message(message, route)

                    if await self.post_message(route, wrapped, scope.context):
                        entry.sent(route)

        except Exception as e:
            report_error(self.logger, "sending message", e)

    def wrap_message(self, message: ClearText, route: MessageRoute) -> PrismMessage:
        pseudonym = Pseudonym.from_address(message.receiver, self.config.pseudonym_salt)

        if message.use_ibe:
            message_to_recipient = message.to_prism()
            encrypted_message_to_recipient = encrypt_user_message(
                self.ibe,
                message.receiver,
                message_to_recipient,
            )
        else:
            encrypted_message_to_recipient = PrismMessage.decode(message.message_bytes)

        dropbox_message = self.dropboxes.write_request(
            route.target,
            pseudonym,
            encrypted_message_to_recipient,
            message.context
        )
        return route.wrap(dropbox_message)

    @property
    def my_dropboxes(self):
        return self.servers.dropboxes_for_recipient(
            self.pseudonym,
            self.config.dropbox_count,
            self.config.dropboxes_per_client,
            self.current_epoch,
        )

    async def make_poll_request(self):
        dropboxes = self.my_dropboxes

        if not dropboxes:
            if frequency_limit("no-dropboxes"):
                self.logger.debug("Could not find any dropboxes to poll.")

        for dropbox in dropboxes:
            if self.dropboxes.should_poll(dropbox):
                await self.poll_dropbox(dropbox)

    async def poll_dropbox(self, dropbox: ServerRecord):
        request_id = make_nonce()
        route = find_route(self.servers, self.current_transport, dropbox, self.config.onion_layers, [])

        if not route:
            if frequency_limit("poll-route"):
                self.logger.debug(f"Failed to find route to {dropbox.name} for polling request")
            return

        with self.trace("poll-request", request_id=request_id.hex()) as scope:
            if self.config.dynamic_links and not dropbox.ark.link_addresses:
                request_links = self.return_links
            else:
                request_links = []

            request = self.dropboxes.read_request(dropbox, self.pseudonym, request_id, request_links, scope.context)
            expiration = self.dropboxes.expiration()
            if expiration:
                expiration = datetime.fromtimestamp(expiration)
            else:
                expiration = "once"
            onion_message = route.wrap(request)

            scope.debug(f"Polling (req: {request_id.hex()[:6]}, expiration: {expiration}): {dropbox}")
            scope.debug(f"Poll route: {route}")

            if await self.post_message(route, onion_message, scope.context):
                self.dropboxes.did_poll(dropbox)

    async def post_message(self, route: MessageRoute, message: PrismMessage, context: SpanContext) -> bool:
        target = route.head
        message = message.clone(epoch=self.current_epoch)
        self.logger.debug(f"Posting to {target.name}: {message}")

        with self.trace("post-message", context) as scope:
            address = next(address for address in target.ark.link_addresses if address.channel_id == route.channel)
            success = await self.current_transport.send_to_address(address, message, scope.context, target.name)

            if not success:
                scope.error(f"Posting message to {address} failed.")
            return success

    def process_encrypted_mpc_dropbox_response(self, message: PrismMessage, context: SpanContext):
        if not self.dropboxes.registry.is_mine(message):
            return

        with self.trace("reassemble-message", context) as scope:
            try:
                encrypted_user_message = self.dropboxes.registry.reassemble(message)
                self.process_message(encrypted_user_message, context)
            except Exception as e:
                scope.error(f"Error reassembling message from {message}: {e}")

    def process_encrypted_registration_message(self, message: PrismMessage, context: SpanContext):
        with self.trace("bootstrap-receive", context,
                        nth_key=len(self.registration_keys) + 1, total_keys=len(self.registration_nonces)) as scope:
            inner_response = decrypt(message, private_key=self.registration_halfkey)
            assert inner_response.msg_type == TypeEnum.CLIENT_REGISTRATION_RESPONSE
            assert inner_response.messagetext is not None
            assert inner_response.nonce == self.registration_nonces[inner_response.name]

            self.registration_keys[inner_response.name] = inner_response.messagetext
            scope.debug(f"Received private key ({len(self.registration_keys)}/{len(self.registration_nonces)}) "
                        f"from registration committee")

        if len(self.registration_keys) == len(self.registration_nonces):
            self.ibe.load_private_keys(self.registration_keys.values())

    def process_encrypted_user_message(self, message: PrismMessage, context: SpanContext):
        try:
            inner = decrypt_user_message(self.ibe, message)
            clear = ClearText.from_prism(inner, self.config.name)
            clear.receive_time = posix_utc_now()

            if self.outgoing_dedupe.is_msg_new(clear.nonce):
                with self.trace("receive-message",
                                context,
                                sender=clear.sender,
                                recipient=clear.receiver,
                                message=clear.message) as scope:
                    clear.context = scope.context
                    scope.debug(f"Cleartext received ({clear.trace_id}): {clear}")
                    self.message_store.record(clear)
                    if self.delegate:
                        self.delegate.message_received(clear)
        except:
            pass

    def process_arks(
            self,
            arks: PrismMessage,
            context: SpanContext
    ):
        sample_ark = cast(PrismMessage, arks.submessages[0])
        arks_epoch = sample_ark.epoch
        with self.trace("process-arks", arks, origin_epoch=arks.epoch, arks_epoch=arks_epoch) as scope:
            timestamp = datetime.utcfromtimestamp(arks.micro_timestamp / 1e6)
            for ark in arks.submessages:
                ark: PrismMessage
                self.process_ark(ark, context, source=arks.pseudonym, timestamp=timestamp)

            origin = self.servers[arks.pseudonym]
            nametag = arks.pseudonym.hex()[:6]
            if origin:
                nametag = f"{origin.name} ({nametag})"

            scope.debug(f"Processing {len(arks.submessages)} ARKs from {nametag}")

        if origin:
            origin.last_broadcast = datetime.utcnow()
            if origin not in self.connected_emixes and origin.epoch == self.current_epoch:
                frequency_limit_reset("link-maintenance-emix")
                self.connected_emixes.append(origin)

        if arks.dead_servers:
            self.process_nark(arks, context)

    def process_ark(
            self,
            ark: PrismMessage,
            _context: SpanContext,
            source: Optional[bytes] = None,
            timestamp: Optional[datetime] = None
    ):
        # trace if valid server count has changed:
        previous_reachable_servers = len(self.servers.reachable_servers)
        if verify_ARK(ark, None, self.pki.root_cert):
            server = self.servers.record(ark)
            if source and timestamp:
                self.servers.update_status(source, server.pseudonym, timestamp, reachable=True)
                self.servers.save()
        else:
            self.logger.warning(f"Could not verify ARK {str(ark)}")

        current_reachable_servers = len(self.servers.reachable_servers)
        if previous_reachable_servers != current_reachable_servers:
            with self.trace("valid-servers", epoch=self.current_epoch, count=current_reachable_servers):
                pass

    def process_nark(self, nark: PrismMessage, _context: SpanContext):
        timestamp = datetime.utcfromtimestamp(nark.micro_timestamp / 1e6)
        for server in nark.dead_servers:
            self.servers.update_status(nark.pseudonym, server, timestamp, reachable=False)
        self.servers.save()

    @contextmanager
    def trace(
            self,
            operation: str,
            parent: Optional[Union[PrismMessage, SpanContext]] = None,
            *joining: Union[PrismMessage, SpanContext],
            **kwargs
    ) -> Generator[PrismScope, None, None]:
        tags = {"client": self.config.name, "epoch": self.current_epoch, **kwargs}

        with trace_context(self.logger, operation, parent, *joining, **tags) as scope:
            yield scope

    def dump_links(self, title: str, links: List[Link]):
        self.logger.debug(f"{title} links:")
        for link in links:
            self.logger.debug(f"  {link}")

    def debug_dump(self, logger):
        logger.debug(f"\n\nDumping Debug Info (epoch {self.current_epoch})\n==================\n")
        dump_config(logger)
        logger.debug(f"My dropboxes: {self.my_dropboxes}")
        my_indices = self.pseudonym.dropbox_indices(configuration.dropbox_count, configuration.dropboxes_per_client)
        logger.debug(f"My dropbox indices: {my_indices}")
        logger.debug("Current Transport\n=================")
        self.current_transport.debug_dump(logger)
        logger.debug("\nBase Transport\n==============")
        self.base_transport.debug_dump(logger)

        self.servers.debug_dump(logger)

        self.dump_links("ARK", self.ark_links)
        self.dump_links("Dropbox", self.dropbox_links)
        self.dump_links("EMIX Broadcast", self.emix_broadcast_links)
        self.dump_links("Return", self.return_links)

    async def load_genesis_links(self, genesis_info: GenesisInfo):
        while not genesis_info.loaded:
            for profile in genesis_info.unloaded_receive_links:
                link = await self.current_transport.load_profile(profile)
                if not link:
                    self.logger.warning(f"Failed to load genesis link profile: {profile}")
                    continue

                dropbox_neighbors = [neighbor for neighbor in genesis_info.neighbors
                                     if neighbor.name in link.endpoints and neighbor.tag == "dropbox"]
                emix_neighbors = [neighbor for neighbor in genesis_info.neighbors
                                  if neighbor.name in link.endpoints and neighbor.tag == "emix"]

                if dropbox_neighbors:
                    self.dropbox_links.append(link)
                if emix_neighbors:
                    self.emix_broadcast_links.append(link)
            await trio.sleep(1.0)
