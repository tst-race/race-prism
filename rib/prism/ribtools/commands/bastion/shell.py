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
from argparse import ArgumentParser
from typing import List

from prism.ribtools.command import BastionCommand
from prism.ribtools.name import race_name

from ..log import shorthand_regex
from ...error import PRTError


class Shell(BastionCommand):
    """Drop into a shell inside the specified docker container, using the same shorthand as prt log."""

    aliases = ["sh"]

    shorthand: str = None
    remote_command: List[str] = []

    def run(self):
        d = self.ensure_current()
        match = shorthand_regex.match(self.shorthand)
        if not match:
            raise PRTError(f"Invalid shorthand {self.shorthand}")

        groups = match.groupdict()
        node_type = "client" if groups["scope"] == "c" else "server"
        node_num = int(groups["node_num"])
        node_name = race_name(node_type, node_num)

        cmd = self.ssh_command(node_name, self.remote_command)
        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("shorthand", metavar="SHORTHAND", help="Node shorthand. See prt log -h for details.")
        parser.add_argument(
            "remote_command", metavar="COMMAND", nargs="*", help="A command to invoke on the remote machine."
        )
