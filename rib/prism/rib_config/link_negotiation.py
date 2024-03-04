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

import json
import random
from pathlib import Path
from typing import List, Iterable, Set

from prism.config.config import Configuration
from prism.config.environment.link import Link
from prism.common.transport.enums import TransmissionType, ConnectionType
from prism.config.error import ConfigError
from prism.config.node import Client

from .channel import Channel
from .link_request import LinkRequest


def fulfill_link(config: Configuration, channel: Channel, link: Link) -> List[LinkRequest]:
    """Generates a set of link requests that will allow this channel to fulfill the given link."""
    requests = []

    if len(link.members) == 2:
        members = list(link.members)
        a = members[0].name
        b = members[1].name
        linkname = f"unicast:{channel.channel_gid}:{a}<->{b}"
    else:
        linkname = f"multicast:{channel.channel_gid}:{hash(link)}"

    if link.tags:
        linkname += ":" + ":".join(link.tags)

    for sender in link.senders:
        receivers = link.receivers.difference({sender})
        if isinstance(sender, Client):
            receivers = filter(lambda n: not isinstance(n, Client), receivers)

        if channel.transmission_type == TransmissionType.MULTICAST and config.multicast:
            requests.append(LinkRequest([channel], sender, receivers, linkname))
        else:
            requests.extend(LinkRequest([channel], sender, {receiver}, linkname) for receiver in receivers)

    return requests


def requests_for_link(
    link: Link, channels: Iterable[Channel], config: Configuration
) -> List[LinkRequest]:
    best_channel_score = max(channel.score_for_link(link) for channel in channels)
    link_channels = [channel for channel in channels if channel.score_for_link(link) == best_channel_score]

    if not link_channels or best_channel_score == 0:
        raise ConfigError(f"No channels found compatible with {link}")

    if link.connection_type == ConnectionType.INDIRECT and config.indirect_channel_choices:
        channel_choices = config.indirect_channel_choices
    else:
        channel_choices = config.direct_channel_choices

    link_channels = random.choices(link_channels, k=min(channel_choices, len(link_channels)))
    # print(f"Channels for {link}: {[c.channel_gid for c in link_channels]}")
    return [request for channel in link_channels for request in fulfill_link(config, channel, link)]


def generate_link_requests(needed_links: Iterable[Link], channels: Iterable[Channel], config: Configuration) -> dict:
    requests = []

    for link in needed_links:
        for request in requests_for_link(link, channels, config):
            requests.append(request)

    return {"links": [request.as_dict() for request in requests]}


def split_channels(requests: Set[LinkRequest]) -> Set[LinkRequest]:
    return {
        LinkRequest({channel}, request.sender, request.recipients, request.group_id)
        for request in requests
        for channel in (request.channels or ["unknown"])
    }


def link_fulfillment_complete(requested_links: dict, fulfilled_links: dict) -> bool:
    reqs = {LinkRequest.from_dict(d) for d in requested_links["links"]}
    fulfilled = {LinkRequest.from_dict(d) for d in fulfilled_links["links"]}
    split_reqs = split_channels(reqs)
    split_fulfilled = split_channels(fulfilled)

    return split_reqs == split_fulfilled


def generation_status(status_path: Path, success: bool, reason: str) -> dict:
    attempt = 0
    if status_path.exists():
        old_status = json.loads(status_path.read_text())
        if old_status:
            attempt = old_status.get("attempt", 0) + 1

    if success:
        status = "complete"
    else:
        status = "in progress"

    return {"attempt": attempt, "reason": reason, "status": status}
