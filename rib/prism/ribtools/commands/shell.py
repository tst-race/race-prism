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

from prism.ribtools.deployment import DeploymentMode
from prism.ribtools.name import shorthand_to_node

from ..command import ExternalCommand
from ..error import PRTError


class Shell(ExternalCommand):
    """Drop into a shell inside the specified docker container, using the same shorthand as prt log."""

    aliases = ["sh"]

    shorthand: str = None
    shell_command: List[str] = None

    def run(self):
        d = self.ensure_current()

        if d.mode == DeploymentMode.aws:
            ip = self.ensure_aws().bastion_ip()
            if not ip:
                raise PRTError("Bastion IP not available yet.")

            if not self.shorthand:
                self.ssh(["ssh"], capture_output=False)
            else:
                self.ssh_forward()
            return

        node_name = shorthand_to_node(self.shorthand)

        if self.shell_command:
            cmd = ["docker", "exec", "-it", node_name, *self.shell_command]
        else:
            cmd = ["docker", "exec", "-it", node_name, "/bin/bash"]

        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("shorthand", metavar="SHORTHAND", nargs="?")
        parser.add_argument("shell_command", metavar="COMMAND", nargs="*")
