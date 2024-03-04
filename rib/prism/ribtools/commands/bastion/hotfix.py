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
from pathlib import Path

from prism.ribtools.command import BastionCommand
from prism.ribtools.error import PRTError


class Hotfix(BastionCommand):
    """Push updated plugin artifacts to all nodes."""

    clients: int = 0
    servers: int = 0

    def run(self):
        release_path = Path.home() / "release.tgz"
        if not release_path.exists():
            raise PRTError("No release tarball found.")

        if (self.clients + self.servers) == 0:
            d = self.ensure_current()
            self.clients = d.client_count
            self.servers = d.server_count

        clients = [f"race-client-{i:05}" for i in range(1, self.clients + 1)]
        servers = [f"race-server-{i:05}" for i in range(1, self.servers + 1)]
        nodes = clients + servers

        self.subprocess(["bash", "deploy_hotfix.sh", *nodes], capture_output=False, cwd=Path(__file__).parent)
        print("Hotfixes deployed.")

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("--clients", metavar="N", type=int, default=0, help="The number of clients to hotfix.")
        parser.add_argument("--servers", metavar="N", type=int, default=0, help="The number of servers to hotfix.")
