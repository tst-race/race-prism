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
from typing import Optional

from prism.ribtools.environment import environment
from prism.ribtools.error import PRTError

from ..command import RIBCommand


class Channel(RIBCommand):
    """Commands for manipulating the channels of the active deployment."""

    aliases = ["ch"]
    channel_command: str = None
    channel: Optional[str] = None

    def run(self):
        subcmd = self.channel_command

        if subcmd == "add":
            d = self.ensure_current()
            d.comms_channels.append(self.channel)
            d.save()
        elif subcmd in ["remove", "rm"]:
            d = self.ensure_current()
            target_channels = [ch for ch in d.comms_channels if self.channel in ch]
            if not target_channels:
                raise PRTError(f"No channels found matching {self.channel} in {d.name}.")
            for ch in target_channels:
                d.comms_channels.remove(ch)
            d.save()
        elif subcmd in ["list", "ls"]:
            cmd = ["rib", "race", "channel", "list", "--race", environment.race_version]
            self.subprocess(cmd)
        elif subcmd == "revisions":
            cmd = ["rib", "race", "channel", "revisions", "--race", environment.race_version, "--channel", self.channel]
            self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser):
        channel_commands = parser.add_subparsers(dest="channel_command")
        add_channel = channel_commands.add_parser("add", help="Add a new channel.")
        add_channel.add_argument("channel", metavar="NAME", help="The channel to add to the current deployment.")
        remove_channel = channel_commands.add_parser("remove", aliases=["rm"], help="Remove a channel.")
        remove_channel.add_argument(
            "channel", metavar="NAME", help="The channel to remove from the current deployment."
        )
        channel_commands.add_parser("list", aliases=["ls"], help="List available channels.")
        revisions_channel = channel_commands.add_parser("revisions", help="List all revisions of a given channel.")
        revisions_channel.add_argument("channel", metavar="CHANNEL", help="The channel to look up revisions for.")
