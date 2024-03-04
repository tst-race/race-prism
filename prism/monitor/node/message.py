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

import statistics
from dataclasses import dataclass, field
from typing import Optional, List, Dict

MESSAGE_FIELDS = {"checksum", "size", "nonce", "sender", "receiver", "sent_time", "trace_id", "recv_time"}
MESSAGE_INT_FIELDS = {"size", "nonce", "sent_time", "recv_time"}


@dataclass(eq=True, frozen=True)
class Message:
    """Represents a the event of a message being sent or received by a client."""

    checksum: str
    size: int
    nonce: int
    sender: str
    receiver: str
    sent_time: int
    trace_id: str
    recv_time: Optional[int] = field(default=None, compare=False, hash=False)

    @staticmethod
    def from_dict(d: dict) -> Message:
        msg_dict = {}
        for k, v in d.items():
            if k in MESSAGE_INT_FIELDS:
                msg_dict[k] = int(v)
            elif k in MESSAGE_FIELDS:
                msg_dict[k] = v

        return Message(**msg_dict)

    def is_send(self) -> bool:
        return not self.recv_time

    def is_recv(self) -> bool:
        return bool(self.recv_time)

    def match(self, other: Message) -> bool:
        """Returns True if self and other make a matched send-receive pair."""
        return self == other and self.is_recv() != other.is_recv()


@dataclass
class MessagePair:
    """Represents a matched send/receive pair of message events."""

    send: Optional[Message] = None
    receive: Optional[Message] = None

    @staticmethod
    def match(msg1: Message, msg2: Message) -> Optional[MessagePair]:
        if not msg1.match(msg2):
            return None

        if msg1.is_send():
            return MessagePair(send=msg1, receive=msg2)
        else:
            return MessagePair(send=msg2, receive=msg1)

    def latency(self) -> float:
        latency_us = self.receive.recv_time - self.receive.sent_time
        return float(latency_us) / 1_000_000.0


@dataclass
class MessageChecker:
    """Collects aggregate statistics about messages sent and received."""

    sent_count: int = 0
    received_count: int = 0
    total_latency: float = 0.0
    avg_latency: Optional[float] = None
    unmatched: Dict[Message, Message] = field(default_factory=dict)
    matched: List[MessagePair] = field(default_factory=list)
    errors: List[Message] = field(default_factory=list)

    def process(self, msg: Message):
        if msg in self.unmatched:
            other = self.unmatched[msg]
            pair = MessagePair.match(msg, other)

            if not pair:
                self.errors.append(msg)
                return

            del self.unmatched[msg]
            self.total_latency += pair.latency()
            self.matched.append(pair)
        else:
            self.unmatched[msg] = msg

        if msg.is_send():
            self.sent_count += 1
        else:
            self.received_count += 1

        if self.matched:
            self.avg_latency = self.total_latency / len(self.matched)

    def stats(self) -> dict:
        if len(self.matched) > 10 and hasattr(statistics, "quantiles"):
            latencies = [pair.latency() for pair in self.matched]
            percentiles = statistics.quantiles(latencies, n=10, method="inclusive")
        else:
            percentiles = None

        return {
            "sent": self.sent_count,
            "received": self.received_count,
            "matched": len(self.matched),
            "unmatched": list(self.unmatched.values()),
            "avg_latency": self.avg_latency,
            "percentiles": percentiles,
        }
