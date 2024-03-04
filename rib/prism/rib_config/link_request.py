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
from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, Union

from prism.config.node import Node

from .channel import Channel


@dataclass(unsafe_hash=True)
class LinkRequest:
    channels: FrozenSet[str]
    sender: str
    recipients: FrozenSet[str]
    # WARNING - group_id field removed from hashing and comparison to work around
    # Core bug where groupId is not respected when merging link requests.
    group_id: str = field(compare=False, hash=False)

    def __init__(
        self,
        channels: Iterable[Union[str, Channel]],
        sender: Union[str, Node],
        recipients: Iterable[Union[str, Node]],
        group_id: str,
    ):
        channels = list(channels)
        if isinstance(channels[0], Channel):
            channels = [channel.channel_gid for channel in channels]
        self.channels = frozenset(channels)

        if isinstance(sender, Node):
            sender = sender.name
        self.sender = sender

        recipients = list(recipients)
        if isinstance(recipients[0], Node):
            recipients = [node.name for node in recipients]
        self.recipients = frozenset(recipients)

        self.group_id = group_id

    def as_dict(self) -> dict:
        return {
            "channels": sorted(self.channels),
            "details": {},
            "groupId": self.group_id,
            "sender": self.sender,
            "recipients": sorted(self.recipients),
        }

    @staticmethod
    def from_dict(d: dict) -> LinkRequest:
        return LinkRequest(
            channels=d.get("channels", ["unknown"]), sender=d["sender"], recipients=d["recipients"], group_id=d["groupId"]
        )
