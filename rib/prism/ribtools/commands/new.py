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
from typing import List

from prism.ribtools.deployment import Deployment, DeploymentMode
from prism.ribtools.error import PRTError

from ..command import RIBCommand


class New(RIBCommand):
    """Create and activate a new deployment."""

    aliases = ["n"]

    name: str = None
    copy: bool = False
    aws: bool = False
    channels: List[str] = None
    size: str = None

    def pre_run(self):
        super().pre_run()
        if Deployment.exists(self.name):
            raise PRTError(f"Deployment {self.name} already exists.")

    def run(self):
        if self.copy:
            d = self.ensure_current()
            d.name = self.name
        else:
            d = Deployment(self.name)

        if self.size:
            try:
                clients, servers = self.size.split("x")
                d.client_count, d.server_count = int(clients), int(servers)
            except (AttributeError, KeyError, ValueError, TypeError):
                raise PRTError("Invalid size.")

        if self.aws:
            d.mode = DeploymentMode.aws
            d.rib_flags = ["--fetch-plugins-on-start", "--colocate"]

        if self.channels:
            d.comms_channels = self.channels

        d.save()
        d.make_current()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument("--copy", action="store_true", help="Create a copy of the current deployment.")
        parser.add_argument(
            "--channel",
            metavar="CHANNEL",
            dest="channels",
            action="append",
            help="Channel to use instead of the defaults.",
        )
        parser.add_argument("--size", metavar="CLIENTSxSERVERS", help="The size of the deployment (default 2x4).")
        parser.add_argument("--aws", action="store_true", help="Create an AWS mode deployment.")
        parser.add_argument("name", metavar="NAME", help="The name of the new deployment.")
