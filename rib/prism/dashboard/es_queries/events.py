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
from dataclasses import dataclass, field, fields
import datetime as dt
from typing import *


@dataclass
class AbstractEvent:
    pass  # subclasses specify fields here; first field is Pandas DataFrame index!

    @classmethod
    def get_index(cls):
        felder = fields(cls)
        if len(felder) == 0:
            raise RuntimeError("Need at least one field declared as Index")
        return felder[0].name

    @staticmethod
    def source_fields():
        return []


@dataclass
class ReceiveEvent(AbstractEvent):
    traceID: str
    root: str
    endTimeMillis: int
    endTime: dt.datetime
    messageSize: int
    messageHash: str = field(default="")
    startTimeMillis: int = field(default=0)
    startTime: dt.datetime = field(default=None)
    network_manager_latency: float = field(default=0.0)
    comms_latency: float = field(default=0.0)
    latency: float = field(default=0.0)
    comms_estimated: float = field(default=0.0)

    @staticmethod
    def source_fields():
        return [
            "startTimeMillis",
            "duration",
            "operationName",
            "tags",
            "spanID",
            "traceID",
        ]


@dataclass
class Spandata(AbstractEvent):
    spanID: str
    traceID: str
    startTimeMillis: int
    durationMicro: int
    opName: str
    hostName: str
    channelID: str

    @staticmethod
    def source_fields():
        return [
            "startTimeMillis",
            "operationName",
            "process.serviceName",
            "tags",
            # "process.tags" -> name = [tag["value"] for tag in result['process']['tags'] if tag["key"] == "hostname"][0]
            "duration",
            "references",
            "spanID",
            "traceID",
        ]
