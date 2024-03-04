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

import requests
from prism.ribtools.commands.clean import Clean as RIBClean
from requests.exceptions import ConnectionError

from ...command import BastionCommand


class Clean(BastionCommand):
    whiteboard: bool = False

    def run(self):
        d = self.ensure_current()
        clients = [f"race-client-{i:05}" for i in range(1, d.client_count + 1)]
        servers = [f"race-server-{i:05}" for i in range(1, d.server_count + 1)]
        nodes = clients + servers

        self.subprocess(["bash", "deploy_cleaner.sh", *nodes], capture_output=False, cwd=Path(__file__).parent)

        self.restart_monitor()

        if self.whiteboard:
            self.clean_whiteboard()

    def restart_monitor(self):
        (Path.home() / ".restart_monitor").touch()

    def clean_whiteboard(self):
        if self.whiteboard:
            try:
                requests.get("http://twosix-whiteboard:5000/resize/0")
            except ConnectionError:
                pass

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("--whiteboard", action="store_true", help="Attempt to clear the TwoSix whiteboard.")


Clean.__doc__ = RIBClean.__doc__
