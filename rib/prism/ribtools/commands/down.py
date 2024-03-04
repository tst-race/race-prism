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

from ..command import RIBCommand
from prism.ribtools.environment import environment


class Down(RIBCommand):
    """Bring the active deployment down."""

    aliases = ["d"]

    force: bool = False

    def run(self):
        d = self.ensure_current()
        cmd = self.deployment_boilerplate(d, "down")
        if self.force:
            cmd.append("--force")
        self.subprocess(cmd)

        # remove any prior Bastion IP (if present)
        environment.bastion_ip_path.unlink(missing_ok=True)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("-f", "--force", action="store_true", help="Pass the --force switch to RIB.")
