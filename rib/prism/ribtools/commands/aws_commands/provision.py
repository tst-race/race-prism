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

from prism.ribtools.error import PRTError

from ...command import RIBCommand


class Provision(RIBCommand):
    """Provision the active environment.."""

    force: bool = False
    timeout: int = None

    def run(self):
        e = self.ensure_aws()
        cmd = self.environment_boilerplate(e, "provision")

        if self.force:
            cmd.append("--force")

        if self.timeout:
            cmd.extend(["--timeout", str(self.timeout)])

        result = self.subprocess(cmd)

        if result.returncode:
            raise PRTError(f"Something went wrong provisioning environment {e.name}")

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument(
            "-f", "--force", action="store_true", help="Pass --force to the RIB command."
        )
        parser.add_argument(
            "--timeout", type=int, default=3600, help="The RIB operation timeout in seconds (default 3600)"
        )
