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
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional

from .message import Message, MessageChecker
from .node import Node
from .parser import Parser
from prism.monitor.reader import LogLine

TESTAPP_PARSERS = {
    "send": Parser(
        r"INFO: Sending message: checksum: (?P<checksum>\w+), size: (?P<size>\d+), nonce: (?P<nonce>\d+), from: (?P<sender>[^,]+), to: (?P<receiver>[^,]+), test-id: (?P<test_id>.*), sent-time: (?P<sent_time>\d+), traceid: (?P<trace_id>[^,]+)"
    ),
    "receive": Parser(
        r"INFO: Received message: checksum: (?P<checksum>\w+), size: (?P<size>\d+), nonce: (?P<nonce>\d+), from: (?P<sender>[^,]+), to: (?P<receiver>[^,]+), test-id: (?P<test_id>.*), sent-time: (?P<sent_time>\d+), traceid: (?P<trace_id>[^,]+), recv-time: (?P<recv_time>\d+)"
    ),
}


def datafy(cls, dct):
    fields = {k: v for k, v in dct.items() if k in cls.__dataclass_fields__}
    return cls(**fields)


@dataclass
class ClientStats:
    monitor_ts: datetime
    backlog: int
    valid_server_count: int
    expired_server_count: int
    avg_time_to_expiry: float
    polling: bool
    monitor_interval: int


class Client(Node):
    stats: Optional[ClientStats]

    def __init__(self, name: str, epoch: str, checker: MessageChecker):
        super().__init__(name, epoch)
        self.sent: List[Message] = []
        self.received: List[Message] = []
        self.checker = checker
        self.dropboxes = []
        self.stats = None

    def parse(self, line: LogLine) -> bool:
        if super().parse(line):
            return True

        if line.file_type == "testapp":
            return self.parse_text_line(TESTAPP_PARSERS, self.parse_testapp, line)
        elif line.file_type == "monitor":
            if "epoch" in line.values and line.values["epoch"] != self.epoch:
                return True  # don't further evaluate this line

            line.values["monitor_ts"] = datetime.fromisoformat(line.values["monitor_ts"])
            self.first_activity = min(self.first_activity, line.values["monitor_ts"])
            self.last_activity = line.values["monitor_ts"]
            self.monitor_interval = line.values["monitor_interval"]
            self.stats = datafy(ClientStats, line.values)
        else:
            raise ValueError(f"Unknown log file type: {line.file_type}")

    def parse_testapp(self, label: str, match: Dict[str, str]):
        msg = Message.from_dict(match)

        if label == "send":
            self.sent.append(msg)
        elif label == "receive":
            self.received.append(msg)

        self.checker.process(msg)
