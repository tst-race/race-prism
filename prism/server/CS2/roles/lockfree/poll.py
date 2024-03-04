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

import random
from dataclasses import dataclass, field
from datetime import datetime
from functools import reduce
from typing import Optional, Dict, Set, List

import structlog
from jaeger_client import SpanContext

from prism.server.CS2.roles.lockfree.peer import DropboxPeer
from prism.common.transport.transport import Link
from prism.common.message import PrismMessage, TypeEnum, HalfKeyMap, LinkAddress
from prism.common.crypto.halfkey.keyexchange import PublicKey
from prism.common.crypto.server_message import encrypt
from prism.common.crypto.util import make_nonce
from prism.common.tracing import extract_span_context, inject_span_context, PrismScope


@dataclass
class Poll:
    nonce: bytes
    half_key: PublicKey
    expiration: Optional[datetime]
    peer_fragments: Dict[int, PrismMessage]
    context: SpanContext
    link_addresses: List[LinkAddress]
    checked_fragments: Set[bytes] = field(default_factory=set)
    links: List[Link] = field(default_factory=list)
    poll_logger = structlog.get_logger(__name__ + " Poll")
    scope: PrismScope = field(default=None)

    def __repr__(self):
        fragment_ids = [frag.hex()[:8] for frag in self.checked_fragments]
        return f"Poll({self.trace}, " \
               f"expires {self.expiration}, " \
               f"return addresses: {self.link_addresses}, " \
               f"checked fragments: {fragment_ids})"

    @property
    def live(self) -> bool:
        return (not self.expiration) or (self.expiration > datetime.utcnow())

    @property
    def trace(self) -> str:
        return self.context and hex(self.context.trace_id)[2:]

    def fragments_to_check(self, peers: List[DropboxPeer], threshold: int, limit: int = 10) -> Set[bytes]:
        """
        Decides on a set of fragments to check against this poll request.
        For simplicity of checking, all fragments in the returned set must be
        available on a single subset of peers of size >= threshold.
        """

        # Step 1. Collect a set of stored fragments from all peers that we haven't already checked.
        fragments = set()
        for peer in peers:
            fragments.update(peer.stored_fragments)
        fragments.difference_update(self.checked_fragments)
        fragments = list(fragments)

        # Step 2. Select a pivot fragment that is available on #peers >= threshold
        pivot = None
        pivot_peers = None
        random.shuffle(fragments)
        for fragment in fragments:
            pivot_peers = [peer for peer in peers if fragment in peer.stored_fragments]
            if len(pivot_peers) >= threshold:
                pivot = fragment
                break

        if not pivot:
            return set()

        # Step 3. Choose up to #limit fragments available on all the same peers as the pivot
        peer_fragments = [peer.stored_fragments for peer in pivot_peers]
        common_fragments = reduce(lambda acc, fragset: acc.intersection(fragset), peer_fragments)
        return set(random.sample(list(common_fragments), min(len(common_fragments), limit)))

    def reply(self, submessages: List[PrismMessage]) -> PrismMessage:
        """Construct a reply to the polling client, given a list of retrieved encrypted submessages."""
        inner = PrismMessage(msg_type=TypeEnum.READ_OBLIVIOUS_DROPBOX_RESPONSE, submessages=submessages)
        context = extract_span_context(submessages[0])

        self.poll_logger.debug(
            f"REPLY: To client request {self.nonce.hex()[:8]} "
            f"with {len(submessages)} fragments, "
            f"tr: {context and hex(context.trace_id)[2:]}"
        )
        my_key = self.half_key.generate_private()
        nonce = make_nonce()
        ciphertext = encrypt(inner, my_key, self.half_key, nonce)

        rep = PrismMessage(
            msg_type=TypeEnum.ENCRYPTED_READ_OBLIVIOUS_DROPBOX_RESPONSE,
            enc_dropbox_response_id=self.nonce,
            ciphertext=ciphertext,
            half_key=HalfKeyMap.from_key(my_key.public_key()),
            nonce=nonce,
        )

        return inject_span_context(rep, context)

    @staticmethod
    def from_message(message: PrismMessage, scope: PrismScope) -> Poll:
        assert message.msg_type == TypeEnum.READ_OBLIVIOUS_DROPBOX

        if message.expiration:
            expiration = datetime.utcfromtimestamp(message.expiration)
        else:
            expiration = None

        addresses = message.link_addresses or []

        msg: PrismMessage
        return Poll(
            nonce=message.nonce,
            half_key=message.half_key.to_key(),
            expiration=expiration,
            peer_fragments={msg.party_id: msg for msg in message.submessages},
            context=scope.context,
            link_addresses=addresses,
            scope=scope,
        )
