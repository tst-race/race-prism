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
import itertools
import math
import os
import time
from datetime import datetime, timedelta
from random import randrange
from typing import List, Callable, Union, Sequence, Optional

import structlog
import trio
from jaeger_client import SpanContext

from prism.common.constant import TIMEOUT_MS_MAX
from prism.common.logging import MPC_LOG
from prism.common.util import frequency_limit
from prism.server.CS2.roles.announcing_role import AnnouncingRole
from prism.server.CS2.roles.lockfree.hook import MPCResponseHook
from prism.server.CS2.roles.lockfree.peer import Peer
from prism.server.CS2.roles.lockfree.preproduct import PreproductStore, Triple, PreproductBatch
from prism.server.CS2.roles.lockfree.sharing import Sharing
from prism.common.transport.enums import ConnectionType
from prism.common.message import TypeEnum, ActionEnum, PrismMessage, MPCMap, Share
from prism.common.config import configuration
from prism.common.crypto.halfkey.keyexchange import KeySystem
from prism.common.crypto.server_message import decrypt, encrypt
from prism.common.crypto.util import make_nonce
from prism.common.tracing import inject_span_context


def mpc_op(a: ActionEnum):
    """A decorator to attach to mpc_ops to make code easier to follow. This allows MPCRole.request() to take the
    op's method as its argument instead of an ActionEnum, and allows MPCRole.mpc_op_handler() to look up which method
    handles a given ActionEnum."""

    def decorator(f):
        f.__annotations__["action_enum"] = a
        return f

    return decorator


class MPCRole(AnnouncingRole):
    """
    A base class for roles that perform MPC operations. Includes management of preproducts such as triples and shared
    random numbers), and MPC operations such as multiplication using triples, which consume those preproducts,
    as well as various helper routines to facilitate common MPC communication patterns.

    Preproducts (random numbers, triples, etc.) are created in batches. Each batch is owned by a specific peer --
    that is, the peer that requested the batch -- and a peer may only initiate retrieve ops using preproducts from
    its own batches.

    Messages are routed using the pair of op_id and action. An operation should generate a random sequence of bytes
    to use as an op_id, and each round of communication within that operation should be labeled with a unique action,
    to make sure that messages intended for one step don't get consumed by a different step.

    MPC methods are organized into tasks, ops, and subroutines.

    Tasks are performed on one peer (the requester) and involve requesting a group of peers to engage in various MPC
    operations (ops). Tasks have the _task suffix.

    Ops are performed on a set of peers simultaneously in lockstep, and end by replying to the original requester.
    Ops have the _op suffix, the @mpc_op annotation, and take a single PrismMessage object as their argument.

    Subroutines are common methods that are used by multiple ops, and may perform rounds of communication. If they do,
    then they should take an op_id argument and use unique actions in their communication rounds.
    """

    peers: List[Peer]
    party_id: int
    preproducts: PreproductStore
    sharing: Sharing = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if configuration.debug_extra:
            self._mpc_logger = structlog.get_logger(MPC_LOG)
        else:
            self._mpc_logger = None

        self.peers = []
        self.party_id = -1

        self.preproducts = PreproductStore(self._logger, self._mpc_logger, self._state_store)
        self.sharing = self.configure_secret_sharing()
        self.has_been_viable = False

    @property
    def ark_ready(self) -> bool:
        return False

    @property
    def is_leader(self) -> bool:
        return self.party_id == 0

    @property
    def is_active_member(self) -> bool:
        return self.party_id != -1

    @property
    def ark_broadcasting(self) -> bool:
        return self.is_leader and not configuration.ls_routing

    def monitor_data(self) -> dict:
        if not self.is_active_member:
            return {
                "party_id": self.party_id,
                **super().monitor_data()
            }

        preproducts_available = self.preproducts.total_remaining([])
        return {
            "party_id": self.party_id,
            "mpc_ready": self.local_peer.ready and (preproducts_available > 0),
            "preproduct_count": preproducts_available,
            "peer_status": [peer.to_dict() for peer in self.peers],
            **super().monitor_data(),
        }

    async def preproduct_task(self):
        """Maintains the store of preproducts, generating new ones when the supply drops below a certain threshold."""

        # For now, peer 0 is considered the 'leader' of the committee and is the only peer that can contact
        # the outside world, and so is the only peer that needs to initiate operations that use preproducts.
        if self.party_id > 0:
            return

        async with trio.open_nursery() as nursery:
            for group in self.preproduct_groups():
                self._logger.debug(f"Launching preproduct task for {group}")
                nursery.start_soon(self.preproduct_group_task, group)

    async def preproduct_group_task(self, group: List[Peer]):
        # TODO Document
        while True:
            batch_size = configuration.mpc_preproduct_batch_size
            min_reserve = batch_size * configuration.mpc_preproduct_refresh_threshold
            remaining = self.preproducts.total_remaining(group, exact=True)
            if remaining < min_reserve:
                if all(self.online(peer) for peer in group):
                    await self.generate_preproduct_task(batch_size, group)
                elif frequency_limit("preproduct-peers-online"):
                    self._logger.warning(f"Not enough peers online for preproducts with peer group {group}")
            await trio.sleep(0.1)

    def preproduct_groups(self) -> List[List[Peer]]:
        """
        Generate all permutations of peers that could be used to generate preproducts.
        Such permutations:
            - Include ourselves (because we will own the produced batch)
            - Are large enough to complete the triple generation process
        """
        peer_combos = []

        for count in range(self.preprocessing_threshold, len(self.peers) + 1):
            for combination in itertools.combinations(self.peers, count):
                if self.local_peer in combination:
                    peer_combos.append(list(combination))

        return peer_combos

    @property
    def preprocessing_threshold(self):
        # The degree of the polynomial we use for secret sharing
        degree = self.sharing.threshold - 1
        # The degree of the polynomial used for degree reduction in multiplication during triple generation,
        # which is also the number of peers needed to generate a batch
        return (2 * degree) + 1

    def timeout_padding(self, rounds: int, bytes_per_peer: int, peer_count: int) -> float:
        """Calculates the amount of time to pad a timeout based on the the estimated round complexity, traffic size,
        and peer count. Does not take into account concurrent tasks/ops, so it should be used in combination with some
        sort of fudge factor."""
        channel_padding = 0.0

        mpc_channels = [ch for ch in self._transport.channels if ch.connection_type == ConnectionType.DIRECT]
        latencies = [ch.latency_ms for ch in mpc_channels if ch.latency_ms > 0]
        bandwidths = [ch.bandwidth_bps for ch in mpc_channels if ch.bandwidth_bps > 0]
        # If no latency estimate is available, guess at 500ms
        worst_latency = (latencies and max(latencies)) or 500
        # If no bandwidth estimate is available, guess 200000bps
        worst_bandwidth = (bandwidths and min(bandwidths)) or 200000

        # Rough estimate of the total number of bytes each node needs to send
        est_data_bits = 8 * bytes_per_peer * (peer_count - 1)

        channel_padding += (worst_latency / 1000) * rounds
        channel_padding += est_data_bits / worst_bandwidth

        return channel_padding

    def preprocessing_batch_timeout(self, batch_size: int, peer_count: int) -> float:
        """The maximum number of seconds to wait for a preproduct batch to be generated before giving up."""
        channel_padding = self.timeout_padding(rounds=6, bytes_per_peer=250 * batch_size, peer_count=peer_count)
        timeout = configuration.mpc_lf_batch_timeout * configuration.mpc_lf_timeout_mult * batch_size + channel_padding
        return timeout

    async def generate_preproduct_task(self, size: int, peers: List[Peer]):
        """
        Generates a batch of preproducts of a certain size with the listed peers.

        Requires 3 rounds of communication.
        """

        batch_id = self.random_id()
        timeout = self.preprocessing_batch_timeout(size, len(peers))

        with self.trace("preprocessing", batch_id=batch_id.hex(), timeout=timeout, peers=peers) as scope:
            scope.debug(f"PRE: Starting Batch {batch_id.hex()[:6]} for {len(peers)} peers: {peers}", timeout=timeout)
            preprocessing_context = scope.context
            batch_request = self.request(
                self.preproduct_op, batch_id, size=size, participants=[peer.party_id for peer in peers]
            )

        start = time.time()
        successes = await self.send_and_gather(peers, batch_request, timeout_sec=timeout, context=preprocessing_context)
        duration = time.time() - start

        if len(successes) >= self.sharing.threshold:
            for success in successes:
                self.peers[success.party_id].preproduct_batches.add(batch_id)
            self.save_committee()
            with self.trace(
                "preprocessing-success", parent=preprocessing_context, batch_id=batch_id.hex(), timeout=timeout
            ) as scope:
                scope.debug(
                    f"PRE: Batch {batch_id.hex()[:6]} succeeded, {len(successes)} responses after {duration}s "
                    f"from peers: {peers}."
                )
        else:
            with self.trace(
                "preprocessing-fail", parent=preprocessing_context, batch_id=batch_id.hex(), timeout=timeout
            ) as scope:
                scope.debug(
                    f"PRE: Batch {batch_id.hex()[:6]} failed, {len(successes)} responses after {duration}s "
                    f"from peers: {peers}."
                )
                if batch_id in self.preproducts.batches:
                    del self.preproducts.batches[batch_id]

    @mpc_op(ActionEnum.ACTION_OFFLINE_INIT)
    async def preproduct_op(self, message: PrismMessage):
        """
        Peer op for preproduct generation. Generates a large batch of shares of random numbers, then uses some of those
        to build shares of triples of the form c=a*b, used in degree reduction during MPC multiplication.
        """
        with self.trace("preprocessing-op", message) as scope:
            batch_id = message.mpc_map.request_id
            size = message.mpc_map.size
            peers = [self.peers[i] for i in message.mpc_map.participants]
            owner = message.party_id
            timeout = self.preprocessing_batch_timeout(size, len(peers))

            scope.debug(f"PRE: Batch {batch_id.hex()[:6]} requested")

            random_shares = await self.generate_shares(
                batch_id, peers, size * 3, timeout_sec=timeout, context=scope.context
            )

            if not random_shares:
                scope.debug(f"PRE: Batch {batch_id.hex()[:6]} failed to generate shares")
                return

            scope.debug(f"PRE: Batch {batch_id.hex()[:6]} shares generated")

            random_numbers = random_shares[size * 2 :]
            a = random_shares[:size]
            b = random_shares[size : size * 2]

            c = await self.mulm_etf(batch_id, peers, a, b, timeout_sec=timeout, context=scope.context)
            if not len(a) == len(b) == len(c) == len(random_numbers):
                self._logger.error(f"PRE: Length check failed: len(a) = {len(a)}, len(b) = {len(b)}, "
                                   f"len(c) = {len(c)}, len(random_numbers) = {len(random_numbers)}")
                return

            if not c:
                scope.error(f"PRE: Batch {batch_id.hex()[:6]} failed to multiply.")
                return

            triples = [Triple(x, y, z) for x, y, z in zip(a, b, c)]

            batch = PreproductBatch(
                batch_id,
                owned=owner == self.party_id,
                peers=set(peer.name for peer in peers),
                random_numbers=random_numbers,
                triples=triples,
            )

            self.preproducts.add_batch(batch)
            scope.debug(f"PRE: Batch {batch_id.hex()[:6]} generated")
            await self.respond_to(message, op_success=True, context=scope.context)

    async def generate_shares(
        self, op_id: bytes, peers: List[Peer], size: int, timeout_sec: float = math.inf, context: SpanContext = None
    ) -> List[Share]:
        """
        Obliviously generates a sequence of random numbers shared by all peers, such that each party
        has a share of each number but does not know what the number is. We accomplish this by having
        each party independently generate a sequence of random numbers, share those numbers, and then
        distribute them such that the i-th party has the i-th shares of each party's number. Summing
        those shares creates shares of a common but unknown random value.

        Requires 1 round of communication.
        """
        random_shares = [self.sharing.share(randrange(1, self.sharing.modulus)) for _ in range(size)]
        peer_shares = await self.distribute_shares(
            op_id, ActionEnum.ACTION_GENERATE_SHARES, peers, random_shares, timeout_sec=timeout_sec, context=context
        )

        if not peer_shares:
            return []

        return [self.sum_shares(shares) for shares in peer_shares]

    def sum_shares(self, shares: Sequence[Share]) -> Share:
        """Sum a sequence of secret shares."""
        v = sum(share.share for share in shares) % self.sharing.modulus
        return Share(v, self.party_id)

    async def mulm_etf(
        self,
        op_id: bytes,
        peers: List[Peer],
        xs: List[Share],
        ys: List[Share],
        timeout_sec: float = math.inf,
        context: SpanContext = None,
    ) -> List[Share]:
        """
        Computes the Hadamard Product of two vectors of shares by multiplying locally then using shared random
        numbers to reduce the degree of the share polynomial back to its original level.

        Requires 2 rounds of communication.
        """
        # The degree of the polynomial evaluated to produce our shares
        low_degree = self.sharing.threshold - 1
        # The degree of the polynomial of a multiplication of shares
        high_degree = low_degree * 2

        # Step 1. Compute [x*y]_high = [x]_low * [y]_low
        xy_high = [self.sharing.mul(x, y) for x, y in zip(xs, ys)]

        # Step 2. Construct low and high degree shares of random numbers, [r]_low and [r]_high
        ss_low = self.sharing
        ss_high = Sharing(nparties=ss_low.nparties, threshold=high_degree + 1, modulus=ss_low.modulus)
        rs = [randrange(1, self.sharing.modulus) for _ in range(len(xs))]
        local_r_low = [ss_low.share(r) for r in rs]
        local_r_high = [ss_high.share(r) for r in rs]
        received_shares = await self.distribute_shares(
            op_id,
            ActionEnum.ACTION_MULM_BGW_RAND,
            peers,
            local_r_low + local_r_high,
            timeout_sec=timeout_sec,
            context=context,
        )
        if not received_shares:
            return []

        r_low_high = [self.sum_shares(shares) for shares in received_shares]

        if not len(r_low_high) == len(xs) * 2:
            self._logger.error(f"PRE: Length check failed: len(r_low_high) = {len(r_low_high)}, len(xs) = {len(xs)}")
            return []

        r_low = r_low_high[: len(xs)]
        r_high = r_low_high[len(xs) :]

        # Step 3. Add high degree random share to high degree product share, resulting in
        # [z]_high = [r-x*y]_high = [r]_high - [x*y]_high
        z_high = [ss_high.sub(r, xy) for r, xy in zip(r_high, xy_high)]

        # Step 4. Open z
        zs = await self.open_multiple(
            op_id, peers, ActionEnum.ACTION_MULM_BGW_OPEN, ss_high, z_high, timeout_sec=timeout_sec, context=context
        )

        if not zs or not all(zs):
            return []

        # Step 5. Return [x*y]_low = [r]_low - (r-x*y)
        result = [ss_low.subc(r, z) for r, z in zip(r_low, zs)]

        if configuration.debug_extra:
            self._mpc_logger.debug(
                "MUL_ETF",
                batch_id=op_id.hex(),
                peers=peers,
                xs=[s.json() for s in xs],
                ys=[s.json() for s in ys],
                low_degree=low_degree,
                high_degree=high_degree,
                xy_high=[s.json() for s in xy_high],
                rs=rs,
                local_r_low=[[s.json() for s in sg] for sg in local_r_low],
                local_r_high=[[s.json() for s in sg] for sg in local_r_high],
                received_shares=[[s.json() for s in sg] for sg in received_shares],
                r_low=[s.json() for s in r_low],
                r_high=[s.json() for s in r_high],
                z_high=[s.json() for s in z_high],
                zs=zs,
                result=[s.json() for s in result],
            )

        return result

    async def open_multiple(
        self,
        op_id: bytes,
        peers: List[Peer],
        action: ActionEnum,
        sharing: Sharing,
        shares: List[Share],
        min_replies: int = None,
        timeout_sec: float = None,
        context: SpanContext = None,
    ) -> List[int]:
        """
        Collectively open a list of shares and return their values.

        Requires 1 round of communication.
        """

        if not timeout_sec:
            timeout_sec = configuration.mpc_lf_base_op_timeout * configuration.mpc_lf_timeout_mult + \
                          self.timeout_padding(2, 64 * len(shares), len(peers))
        share_message = self.response(action, op_id, shares=shares)
        responses = await self.send_and_gather(
            peers, share_message, timeout_sec=timeout_sec, min_replies=min_replies, context=context
        )
        if not responses:
            return []
        all_shares = zip(*(m.mpc_map.shares for m in responses))
        return [sharing.open(shares) for shares in all_shares]

    async def mulm(
        self,
        xs: List[Share],
        ys: List[Share],
        triples: List[Triple],
        peers: List[Peer],
        op_id: bytes,
    ) -> List[Share]:
        """
        Computes the Hadamard Product of two vectors of shares, consuming triples for degree reduction using the BGW
        protocol.

        Consumes len(xs) == len(ys) triples.
        Requires 1 round of communication.
        """
        # TODO - If (threshold-1)*2 < len(peers), then we have enough headroom in the degree
        #        of our polynomial to skip the degree reduction via triple
        # if (self.sharing.threshold - 1) * 2 < len(peers):
        #     return [self.sharing.mul(x, y) for x, y in zip(xs, ys)]
        epsilon_shares = [self.sharing.sub(x, t.a) for x, t in zip(xs, triples)]
        delta_shares = [self.sharing.sub(y, t.b) for y, t in zip(ys, triples)]

        eds = await self.open_multiple(
            op_id,
            peers,
            ActionEnum.ACTION_MUL_HANDLER,
            self.sharing,
            epsilon_shares + delta_shares,
            min_replies=self.sharing.threshold,
        )
        if not eds:
            return []
        epsilon_open = eds[: len(xs)]
        delta_open = eds[len(xs) :]

        return [self.sharing.mul_ed(e, d, t) for e, d, t in zip(epsilon_open, delta_open, triples)]

    async def distribute_shares(
        self,
        op_id: bytes,
        action: ActionEnum,
        peers: List[Peer],
        shares: List[List[Share]],
        timeout_sec: float = math.inf,
        context: SpanContext = None,
    ) -> List[List[Share]]:
        """
        Given a list of lists of shares from each party, redistributes the shares such that the i-th party has the
        i-th share of each inner list.
        """
        requests = [self.response(action, op_id, shares=[share[peer.party_id] for share in shares]) for peer in peers]
        peer_msgs = await self.send_and_gather(peers, requests, len(peers), timeout_sec=timeout_sec, context=context)
        if not peer_msgs:
            return []
        peer_shares = [message.mpc_map.shares for message in peer_msgs]
        return [list(shares) for shares in zip(*peer_shares)]

    def random_id(self) -> bytes:
        """
        Generates a random sequence of bytes to use as MPC operation identifiers.
        """
        return os.urandom(32)

    def request(self, handler: Callable, op_id: bytes = None, **kwargs) -> PrismMessage:
        """
        Helper function for tasks to generate messages for launching ops on peers.
        @param handler: The method associated with the op (must have @mpc_op annotation)
        @param op_id:  A random sequence of bytes to identify this invocation of the operation.
        @param kwargs: Arguments that will be slotted into matching PrismMessage/MPCMap fields.
        """
        # noinspection PyUnresolvedReferences
        action = handler.__annotations__.get("action_enum")
        return self.mpc_message(TypeEnum.MPC_REQUEST, action, op_id, **kwargs)

    def response(self, action: ActionEnum, op_id: bytes, **kwargs) -> PrismMessage:
        """
        Helper function for ops to construct messages for rounds of communication.
        @param action: An ActionEnum that is unique to this step of the operation.
        @param op_id: The op_id for the operation
        @param kwargs: Arguments that will be slotted into matching PrismMessage/MPCMap fields.
        """
        return self.mpc_message(TypeEnum.MPC_RESPONSE, action, op_id, **kwargs)

    async def respond_to(self, message: PrismMessage, context: SpanContext = None, **kwargs):
        """
        Helper function for ops to construct their replies to the requester
        @param message: The message used to request the op
        @param context: The opentracing span context associated with the response
        @param kwargs: Arguments that will be slotted into matching PrismMessage/MPCMap fields.
        """
        peer = self.peers[message.party_id]
        response = self.response(message.mpc_map.action, message.mpc_map.request_id, **kwargs)
        await self.send_to_peer(peer, response, context=context)

    def mpc_message(self, msg_type: TypeEnum, action: ActionEnum, op_id: bytes, **kwargs) -> PrismMessage:
        """Common constructor for MPC messages."""
        prism_kws = {k: v for k, v in kwargs.items() if PrismMessage.lookup_field_index(k) != -1}
        mpc_kws = {k: v for k, v in kwargs.items() if MPCMap.lookup_field_index(k) != -1}

        return PrismMessage(
            msg_type=msg_type,
            party_id=self.party_id,
            mpc_map=MPCMap(action=action, request_id=op_id, **mpc_kws),
            **prism_kws,
        )

    async def send_and_gather(
        self,
        peers: List[Peer],
        messages: Union[PrismMessage, List[PrismMessage]],
        min_replies: int = None,
        timeout_sec: float = math.inf,
        context: SpanContext = None,
    ) -> List[PrismMessage]:
        """
        Send a message to each listed peer and await a response
        @param peers: A list of peers to contact
        @param messages: A single message to send to all peers, or a list of messages in the same order as the peer list
        @param min_replies: The minimum number of replies needed to successfully continue the computation. If omitted,
        then min_replies = len(peers).
        @param timeout_sec: The number of seconds to wait for messages to come in before returning.
        @param context: The opentracing span context associated with the message
        @return: All replies received.
        """
        if not messages:
            # No messages to send, so we return immediately.
            return []
        if isinstance(messages, PrismMessage):
            messages = [messages] * len(peers)

        op_id = messages[0].mpc_map.request_id
        action = messages[0].mpc_map.action

        if not min_replies:
            min_replies = len(peers)

        await self.send_to_peers(peers, messages, context=context, timeout_sec=timeout_sec)
        return await self.gather_responses(op_id, action, count=min_replies, timeout_sec=timeout_sec, context=context)

    async def gather_responses(
        self,
        op_id: bytes,
        action: ActionEnum,
        count: int,
        timeout_sec: float = math.inf,
        context: SpanContext = None,
    ) -> List[PrismMessage]:
        """
        Listen for messages matching the given op_id and action until count messages have been received.
        Return a list of messages sorted by party ID, ascending.
        """
        responses = []
        hook = MPCResponseHook(self.pseudonym, self.party_id, op_id, action)
        try:
            await self._transport.register_hook(hook)
            with trio.move_on_after(timeout_sec):
                while True:
                    response = await hook.receive_pkg()
                    responses.append(response.message)

                    if len(responses) >= count:
                        break
        finally:
            self._transport.remove_hook(hook)

            if len(responses) < count:
                if context:
                    with self.trace(
                        "gather-fail",
                        context,
                        op=op_id.hex(),
                        action=action.name,
                        needed_responses=count,
                        received_responses=len(responses),
                        respondents=[self.peers[resp.party_id].name for resp in responses],
                    ):
                        return []

            return sorted(responses, key=lambda message: message.party_id)

    async def broadcast_to_peers(self, message: PrismMessage, context: SpanContext = None):
        """Broadcast a single message to all non-local peers."""
        peers = [peer for peer in self.peers if not peer.local]
        messages = [message] * len(peers)
        await self.send_to_peers(peers, messages, context=context)

    async def send_to_peers(
            self,
            peers: List[Peer],
            messages: Union[PrismMessage, List[PrismMessage]],
            context: SpanContext = None,
            timeout_sec: float = math.inf,
    ):
        """Send N messages to N peers, in parallel."""
        if not messages:
            # No messages to send, so we return immediately.
            return
        if isinstance(messages, PrismMessage):
            messages = [messages] * len(peers)

        assert len(peers) == len(messages)
        async with trio.open_nursery() as nursery:
            for peer, message in zip(peers, messages):
                nursery.start_soon(self.send_to_peer, peer, message, context, timeout_sec)

    async def send_to_peer(
            self,
            peer: Peer,
            message: PrismMessage,
            context: SpanContext = None,
            timeout_sec: float = math.inf,
    ) -> bool:
        """Send a message to a specific peer."""
        if not peer.local:
            message = self.encrypt_peer_message(peer, message)

        # Add some uniquifying information to keep MPC message hashes distinct
        nonce = message.nonce or make_nonce()
        addressed_message = message.clone(dest_party_id=peer.party_id, nonce=nonce, pseudonym=peer.pseudonym)

        if timeout_sec == math.inf:
            timeout_ms = TIMEOUT_MS_MAX
        else:
            timeout_ms = int(timeout_sec*1000)

        if peer.local:
            return await self._transport.local_link.send(addressed_message, context=context)
        else:
            return await self.router.send(peer.pseudonym, addressed_message, context=context,
                                          block=True, timeout_ms=timeout_ms)

    async def mpc_op_task(self, nursery: trio.Nursery, message: PrismMessage, context: SpanContext):
        """Handles MPC ops requested by peers."""
        action = message.mpc_map.action
        handler = self.handler_for(action)
        if handler:
            self._logger.debug(f"Handling MPC Op: {handler.__name__}")
            nursery.start_soon(handler, self, inject_span_context(message, context))
        else:
            self._logger.error(f"Got request for unknown op: {action}")

    def configure_secret_sharing(self) -> Sharing:
        """Generate a Sharing object for performing secret sharing operations using parameters from config."""
        nparties = configuration.get("mpc_nparties")
        threshold = configuration.get("threshold")
        modulus = configuration.get("mpc_modulus")
        return Sharing(nparties, threshold, modulus)

    async def handshake_task(self):
        while True:
            timeout = configuration.mpc_lf_hello_timeout * configuration.mpc_lf_timeout_mult
            await self.say_hello(timeout)
            await self.say_ready(timeout)
            await trio.sleep(timeout)

    async def say_hello(self, timeout: float):
        hello_peers = [peer for peer in self.peers if not peer.local and not peer.last_hello_ack]

        if not hello_peers:
            return

        hello = self.request(
            self.hello_op,
            self.random_id(),
            half_key=self.local_peer.half_key,
            sender=self.pseudonym,
        )

        self._logger.debug(f"KEY: Sending key info to {hello_peers}.")

        responses = await self.send_and_gather(hello_peers, hello, timeout_sec=timeout)
        for response in responses:
            peer = self.peers[response.party_id]
            self._logger.debug(f"KEY: Got hello ack from {peer}")
            peer.last_hello_ack = datetime.utcnow()

    @mpc_op(ActionEnum.ACTION_HELLO)
    async def hello_op(self, message: PrismMessage):
        assert message.party_id is not None
        assert message.sender is not None
        assert message.half_key
        peer = self.peers[message.party_id]
        peer.half_key = message.half_key
        peer.pseudonym = message.sender
        self._logger.debug(f"KEY: Received halfkey from {peer}")
        self.save_committee()
        await self.respond_to(message, op_success=True)

    async def say_ready(self, timeout: float):
        if not self.ready:
            return

        self.local_peer.ready = True
        ready_peers = [peer for peer in self.peers if not peer.local and not peer.last_ready_ack]

        if not ready_peers:
            return

        ready_msg = self.request(
            self.handle_ready,
            self.random_id(),
        )
        responses = await self.send_and_gather(ready_peers, ready_msg, timeout_sec=timeout)
        for response in responses:
            peer = self.peers[response.party_id]
            self._logger.debug(f"KEY: Got ready ack from {peer}")
            peer.last_ready_ack = datetime.utcnow()

    @mpc_op(ActionEnum.ACTION_READY)
    async def handle_ready(self, message: PrismMessage):
        self.peers[message.party_id].ready = True
        self.save_committee()
        await self.respond_to(message, op_success=True)

    @property
    def ready(self) -> bool:
        """Subclasses should override this method and have it return True when enough bootstrapping has finished for
        MPC operations to begin."""
        return False

    @property
    def viable(self) -> bool:
        online_count = len(self.online_peers)
        viable = online_count >= self.preprocessing_threshold
        self.has_been_viable = viable or self.has_been_viable
        return viable

    @property
    def local_peer(self) -> Peer:
        return self.peers[self.party_id]

    def online(self, peer: Union[Peer, int]) -> bool:
        """
        @param peer: A peer or party ID.
        @return: Whether that peer is online and ready to work.
        """
        if isinstance(peer, int):
            peer = self.peers[peer]
        if peer.local:
            return True
        if not peer.ready:
            return False

        if not self.router.online(peer.pseudonym):
            if frequency_limit(f'peer-{peer.name}-offline', limit=timedelta(seconds=10)):
                self._logger.debug(f"Peer {peer.name} not online because LSP")
            return False

        return True

    @property
    def online_peers(self) -> List[Peer]:
        return [peer for peer in self.peers if self.online(peer)]

    def handler_for(self, action: ActionEnum) -> Callable:
        """
        Figures out the op that should handle an MPC_REQUEST with the given ActionEnum.
        """
        for item in dir(self.__class__):
            attr = getattr(self.__class__, item)
            if not callable(attr) or not hasattr(attr, "__annotations__"):
                continue
            if attr.__annotations__.get("action_enum") == action:
                return attr

    def encrypt_peer_message(self, peer: Peer, message: PrismMessage) -> Optional[PrismMessage]:
        if not peer.half_key or not peer.last_hello_ack or not configuration.mpc_lf_encrypt_peer:
            return message

        nonce = make_nonce()
        peer_key = peer.half_key.to_key()
        ciphertext = encrypt(message, private_key=self.private_key, peer_key=peer_key, nonce=nonce)

        if not ciphertext:
            self._logger.debug(f"Failed to encrypt message for {peer}")
            return message

        return PrismMessage(
            msg_type=TypeEnum.ENCRYPT_PEER_MESSAGE,
            pseudonym=peer.pseudonym,
            ciphertext=ciphertext,
            nonce=nonce,
            party_id=self.party_id,
        )

    async def handle_enc_peer(self, _nursery: trio.Nursery, message: PrismMessage, context: SpanContext):
        source_peer = self.peers[message.party_id]

        if not source_peer.half_key:
            self._logger.debug("Can't decrypt: No peer key")
            return

        peer_key = source_peer.half_key.to_key()
        decrypted = decrypt(message, self.private_key, pub_key=peer_key)
        if decrypted:
            decrypted = decrypted.clone(
                dest_party_id=message.dest_party_id,
                pseudonym=(decrypted.pseudonym or message.pseudonym)
            )
            await self._transport.local_link.send(decrypted, context)

    def debug_dump(self, logger):
        super().debug_dump(logger)
        logger.debug("Peers:")
        for peer in self.peers:
            logger.debug(f"  {peer}")

        logger.debug("\nPreproducts:")
        self.preproducts.debug_dump(logger)

    def save_committee(self):
        # Stub method overridden by subclasses, called whenever peer information changes
        pass

    async def main(self):
        if not self.peers:
            self._logger.error("MPCRole started with no configured peers")
            return

        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)
            nursery.start_soon(self.preproduct_task)
            nursery.start_soon(self.handler_loop, nursery, self.mpc_op_task, True, TypeEnum.MPC_REQUEST)
            nursery.start_soon(self.handler_loop, nursery, self.handle_enc_peer, True, TypeEnum.ENCRYPT_PEER_MESSAGE)
            nursery.start_soon(self.handshake_task)
