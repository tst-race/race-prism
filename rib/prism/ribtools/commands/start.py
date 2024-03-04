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
import time
from typing import List

from prism.ribtools.environment import environment
from prism.ribtools.commands.clean import Clean
from prism.ribtools.name import shorthand_to_node

from ..command import RIBCommand
from ..deployment import DeploymentMode


class Start(RIBCommand):
    """Clean and start the active deployment.

    With arguments, skip cleaning and treat each argument as a node shorthand (see prt log)
    and specifically start the listed nodes."""

    nodes: List[str] = []

    def run(self):
        d = self.ensure_current()

        if not self.nodes:
            if d.mode == DeploymentMode.aws:
                self.ssh_forward(["prt", "clean"])
            else:
                Clean().run()
            # write current time in milliseconds since epoch to LAST_STARTED
            environment.last_started.write_text(f"{round(time.time() * 1000)}")

        cmd = self.deployment_boilerplate(d, "start")

        for node in self.nodes:
            cmd.extend(["--node", shorthand_to_node(node)])

        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("nodes", metavar="NODE", nargs="*")
