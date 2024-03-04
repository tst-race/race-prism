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

from prism.ribtools.name import shorthand_to_node

from ..command import RIBCommand


class Stop(RIBCommand):
    """Stop the active deployment.

    With arguments, treat each argument as a node shorthand and specifically stop the listed nodes."""

    nodes: List[str] = []

    def run(self):
        d = self.ensure_current()
        cmd = self.deployment_boilerplate(d, "stop")

        for node in self.nodes:
            cmd.extend(["--node", shorthand_to_node(node)])

        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("nodes", metavar="NODE", nargs="*")
