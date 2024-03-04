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

import abc
from datetime import datetime, timedelta
from typing import List, Optional, Dict

import structlog
from jaeger_client import SpanContext

from prism.common.crypto.halfkey.keyexchange import PrivateKey
from prism.common.crypto.secretsharing import get_ssobj_from_map, SecretSharing
from prism.common.crypto.server_message import decrypt, decrypt_data
from prism.common.message import PrismMessage, TypeEnum, HalfKeyMap, Share
from prism.common.message_utils import encrypt_message
from prism.common.pseudonym import Pseudonym
from prism.common.server_db import ServerRecord
from prism.common.tracing import trace_context
from prism.common.transport.transport import Link

LOGGER = structlog.getLogger(__name__)


class Dropbox(metaclass=abc.ABCMeta):
    def __init__(self, dropbox: ServerRecord):
        self.dropbox = dropbox
        self.last_polled = datetime.min

    @abc.abstractmethod
    def write_request(self, pseudonym: Pseudonym, message: PrismMessage, context: SpanContext):
        pass

    @abc.abstractmethod
    def read_request(
            self,
            pseudonym: Pseudonym,
            request_id: bytes,
            return_links: List[Link],
            expiration: Optional[int],
            context: SpanContext,
    ):
        pass


class PseudonymDropbox(Dropbox):
    def write_request(self, pseudonym: Pseudonym, message: PrismMessage, context: SpanContext):
        inner_message = PrismMessage(
            msg_type=TypeEnum.WRITE_DROPBOX,
            pseudonym=pseudonym.pseudonym,
            sub_msg=message
        )

        return encrypt_message(self.dropbox, inner_message, include_pseudonym=True)

    def read_request(
            self,
            pseudonym: Pseudonym,
            request_id: bytes,
            return_links: List[Link],
            expiration: Optional[int],
            context: SpanContext,
    ):
        msg_fields = {
            "nonce": request_id,
            "pseudonym": pseudonym.pseudonym,
        }

        if expiration is not None:
            msg_fields["expiration"] = expiration

        if return_links:
            msg_fields["link_addresses"] = [link.address_cbor for link in return_links]

        inner_message = PrismMessage(msg_type=TypeEnum.READ_DROPBOX, **msg_fields)
        return encrypt_message(self.dropbox, inner_message, include_pseudonym=True)


class MPCRequestInfo:
    def __init__(self, server: MPCDropbox, request_id: bytes, key: PrivateKey, peer_keys: Dict[int, PrivateKey]):
        self.server = server
        self.request_id = request_id
        self.key = key
        self.peer_keys = peer_keys

    def peer_key_map(self, party_id: int) -> HalfKeyMap:
        return HalfKeyMap.from_key(self.peer_keys[party_id].public_key())

    def outer_key_map(self) -> HalfKeyMap:
        return HalfKeyMap.from_key(self.key.public_key())

    @classmethod
    def generate(cls, dropbox: MPCDropbox, request_id: bytes) -> MPCRequestInfo:
        return MPCRequestInfo(
            dropbox,
            request_id,
            dropbox.dropbox.public_key().generate_private(),
            {
                party_id: dropbox.dropbox.public_key(party_id).generate_private()
                for party_id, key in enumerate(dropbox.dropbox.ark.worker_keys)
                if key
            }
        )


class MPCDropbox(Dropbox):
    def __init__(self, dropbox: ServerRecord, registry: MPCRequestRegistry, configuration):
        super().__init__(dropbox)
        self.registry = registry
        self.configuration = configuration

    @property
    def secret_sharing(self) -> SecretSharing:
        return get_ssobj_from_map(self.dropbox.ark.secret_sharing)

    def debug_pseudo_shares(self, pseudo_shares: List[List[Share]], context: SpanContext):
        if self.configuration.debug_extra:
            with trace_context(LOGGER, "pseudo-shares", context) as scope:
                for shares in pseudo_shares:
                    share = shares[0]
                    scope.debug(f"Party ID: {share.x}, Share: {share.share}")

    def write_request(self, pseudonym: Pseudonym, message: PrismMessage, context: SpanContext):
        pseudo_shares = self.secret_sharing.share_bytes(pseudonym.pseudonym)
        message_shares = self.secret_sharing.share_bytes(message.encode())

        self.debug_pseudo_shares(pseudo_shares, context)
        submessages = [
            encrypt_message(
                self.dropbox,
                PrismMessage(msg_type=TypeEnum.WRITE_DROPBOX,
                             pseudonym_share=pseudo_shares[party_id][0].share,
                             ciphertext=self.secret_sharing.join_shares(message_shares[party_id])),
                party_id=party_id)
            for party_id, key in enumerate(self.dropbox.ark.worker_keys)
            if key
        ]

        request = PrismMessage(msg_type=TypeEnum.WRITE_OBLIVIOUS_DROPBOX, submessages=submessages)
        return encrypt_message(self.dropbox, request, include_pseudonym=True)

    def read_request(
            self,
            pseudonym: Pseudonym,
            request_id: bytes,
            return_links: List[Link],
            expiration: Optional[int],
            context: SpanContext,
    ):
        request_info = MPCRequestInfo.generate(self, request_id)
        pseudo_shares = self.secret_sharing.share_bytes(pseudonym.pseudonym)

        self.debug_pseudo_shares(pseudo_shares, context)
        submessages = [
            encrypt_message(
                self.dropbox,
                PrismMessage(msg_type=TypeEnum.READ_DROPBOX,
                             pseudonym_share=pseudo_shares[party_id][0].share,
                             half_key=request_info.peer_key_map(party_id)),
                party_id=party_id,
            )
            for party_id, key in enumerate(self.dropbox.ark.worker_keys)
            if key
        ]

        request = PrismMessage(
            msg_type=TypeEnum.READ_OBLIVIOUS_DROPBOX,
            nonce=request_id,
            half_key=request_info.outer_key_map(),
            submessages=submessages,
            link_addresses=[link.address_cbor for link in return_links],
            expiration=expiration
        )

        self.registry.register(request_info)
        return encrypt_message(self.dropbox, request, include_pseudonym=True)


class MPCRequestRegistry:
    def __init__(self):
        self.requests: Dict[bytes, MPCRequestInfo] = {}
        self.logger = LOGGER

    def register(self, request_info: MPCRequestInfo):
        self.requests[request_info.request_id] = request_info

    def is_mine(self, message: PrismMessage) -> bool:
        return message.enc_dropbox_response_id in self.requests

    def reassemble(self, message: PrismMessage) -> Optional[PrismMessage]:
        request = self.requests.get(message.enc_dropbox_response_id)
        if not request:
            return None

        encrypted_fragments = decrypt(message, private_key=request.key)
        if not encrypted_fragments:
            return None

        secret_sharing = request.server.secret_sharing

        frag: PrismMessage
        decrypted_fragments = [
            secret_sharing.split_shares(decrypt_data(frag, private_key=request.peer_keys[frag.party_id]))
            for frag in encrypted_fragments.submessages
        ]

        return PrismMessage.decode(secret_sharing.reconstruct_bytes(decrypted_fragments))


class Dropboxes:
    def __init__(self, configuration):
        self.config = configuration
        self.registry = MPCRequestRegistry()
        self.dropboxes: Dict[bytes, Dropbox] = {}

    def lookup(self, record: ServerRecord) -> Dropbox:
        if record.pseudonym not in self.dropboxes:
            dbx = self.create_dropbox(record)
            self.dropboxes[record.pseudonym] = dbx

        return self.dropboxes[record.pseudonym]

    def create_dropbox(self, record: ServerRecord) -> Dropbox:
        if record.role == "DROPBOX_LF":
            return MPCDropbox(record, self.registry, self.config)
        else:
            return PseudonymDropbox(record)

    def should_poll(self, record: ServerRecord) -> bool:
        db = self.lookup(record)
        interval = timedelta(milliseconds=self.config.poll_timing_ms)
        next_poll = db.last_polled + interval
        return datetime.utcnow() > next_poll

    def did_poll(self, record: ServerRecord):
        db = self.lookup(record)
        db.last_polled = datetime.utcnow()

    def write_request(self, dropbox: ServerRecord, pseudonym: Pseudonym, message: PrismMessage, context: SpanContext) -> PrismMessage:
        db = self.lookup(dropbox)
        return db.write_request(pseudonym, message, context)

    def read_request(
            self,
            dropbox: ServerRecord,
            pseudonym: Pseudonym,
            request_id: bytes,
            return_links: List[Link],
            context: SpanContext,
    ) -> PrismMessage:
        db = self.lookup(dropbox)
        return db.read_request(pseudonym, request_id, return_links, self.expiration(), context)

    def expiration(self):
        if self.config.dropbox_poll_with_duration:
            return (datetime.utcnow() + timedelta(milliseconds=self.config.poll_timing_ms)).timestamp()
        else:
            return None
