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
from datetime import timedelta
from typing import List, Set

from prism.common.config import configuration
from prism.common.transport.channel_select import rank_channels
from prism.common.transport.enums import ConnectionType
from prism.common.transport.transport import Transport, Link
from prism.common.util import frequency_limit


async def maintain_incoming_links(
        logger,
        transport: Transport,
        links: List[Link],
        tags: Set[str],
        return_id: str
):
    incoming_channels = [ch for ch in transport.channels if ch.link_direction.sender_loaded]

    if not incoming_channels and frequency_limit("incoming-channels-unavailable", timedelta(seconds=60)):
        logger.warn(f"No channels available to create incoming links.")

    channels_ranked = rank_channels(incoming_channels, ConnectionType.INDIRECT, tags)
    channels_to_use = channels_ranked[:configuration.incoming_channel_count]

    unused_channels = [channel for channel in channels_to_use
                       if channel.status.usable and
                       not any(link.channel.channel_id == channel.channel_id for link in links)]

    if not unused_channels:
        return

    new_channel = unused_channels[0]
    logger.debug(f"Creating incoming {tags} link on {new_channel}")
    new_link = await new_channel.create_link([return_id])

    if new_link:
        logger.debug(f"Created incoming {tags} link {new_link.link_id}, address: {new_link.link_address}")
        links.append(new_link)
