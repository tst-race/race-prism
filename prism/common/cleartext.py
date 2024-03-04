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

import base64
from dataclasses import dataclass, field
from typing import Optional

from jaeger_client import SpanContext

from prism.common.crypto.util import make_nonce
from prism.common.message import PrismMessage, TypeEnum
from prism.common.tracing import extract_span_context
from prism.common.util import posix_utc_now


@dataclass
class ClearText:
    receiver: str
    sender: str
    message: str = field(default=None)
    message_bytes: bytes = field(default=None)
    nonce: bytes = field(default_factory=make_nonce)
    timestamp: int = field(default_factory=posix_utc_now)
    receive_time: int = field(default=None)
    context: Optional[SpanContext] = field(default=None)
    use_ibe: bool = field(default=True)

    @property
    def nonce_string(self) -> str:
        return self.nonce.hex()

    def __str__(self):
        return f"{self.sender} -> {self.receiver}: {self.message}"

    def to_json(self):
        return {"sender": self.sender, "receiver": self.receiver, "message": self.message}

    def __len__(self):
        total = 0
        if self.message:
            total += len(self.message)
        if self.message_bytes:
            total += len(self.message_bytes)
        return total

    @property
    def trace_id(self):
        if not self.context:
            return None

        return hex(self.context.trace_id)

    def to_prism(self) -> PrismMessage:
        return PrismMessage(
            msg_type=TypeEnum.USER_MESSAGE,
            name=self.sender,
            messagetext=self.message,
            ciphertext=self.message_bytes,
            nonce=self.nonce,
            origination_timestamp=self.timestamp,
        )

    @classmethod
    def from_prism(cls, message: PrismMessage, receiver: str):
        assert message.msg_type == TypeEnum.USER_MESSAGE
        return ClearText(
            receiver=receiver,
            sender=message.name,
            message=message.messagetext,
            message_bytes=message.ciphertext,
            nonce=message.nonce,
            timestamp=message.origination_timestamp,
            context=extract_span_context(message)
        )

    def json(self):
        j = {
            "type": "message",
            "receiver": self.receiver,
            "sender": self.sender,
            "nonce": self.nonce_string,
            "timestamp": self.timestamp,
        }

        if self.message:
            j["message"] = self.message

        if self.message_bytes:
            j["message_bytes"] = base64.b64encode(self.message_bytes)

        if self.receive_time is not None:
            j["receive_time"] = self.receive_time

        return j

    @classmethod
    def from_json(cls, j: dict) -> ClearText:
        del j["type"]

        if "nonce" in j:
            j["nonce"] = bytes.fromhex(j["nonce"])

        if "message_bytes" in j:
            j["message_bytes"] = base64.b64decode(j["message_bytes"])

        return ClearText(**j)
