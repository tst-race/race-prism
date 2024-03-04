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
from typing import Set, List

from prism.common.config import configuration
from prism.common.transport.enums import ConnectionType
from prism.common.transport.transport import Channel


def rank_channels(channels: List[Channel], connection_type: ConnectionType, tags: Set[str]) -> List[Channel]:
    """
    Rank available channels by suitability for a connection.
    Channels that don't match the supplied connection type will be dropped.
    After that, channels are ranked by number of matching tags, then by latency, then by bandwidth.
    """

    channels = [channel for channel in channels
                if channel.connection_type == connection_type]

    # Sort in reverse order of key priority
    channels.sort(key=lambda c: c.bandwidth_bps, reverse=True)
    channels.sort(key=lambda c: c.latency_ms, reverse=True)

    if configuration.strict_channel_tags:
        channels = [c for c in channels if tags.intersection(c.tags)]
    else:
        channels.sort(key=lambda c: len(tags.intersection(c.tags)), reverse=True)

    return channels
