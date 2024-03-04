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
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Tuple, Optional

import trio

from ..command import ExternalCommand
from prism.monitor import Monitor as PMonitor, Reader, DirectoryReader
from prism.ribtools.monitor.files import RIB_FILES, REPLAY_FILES, RIB_DIR_PATTERN
from prism.ribtools.monitor.bastion import BastionReader


class Monitor(ExternalCommand):
    """Run the PRISM monitor."""

    aliases = ["m", "mo", "mon"]
    aws_forward = True

    replay: bool = False
    debug: bool = False
    clients: int = -1
    servers: int = -1
    epoch: str = "genesis"

    def run(self):
        while True:
            try:
                reader, clear_file = self.reader()

                if not reader:
                    time.sleep(1)
                    continue

                mon = PMonitor(
                    reader,
                    replay=self.replay,
                    verbose=self.verbose,
                    debug=self.debug,
                    clear_file=clear_file,
                    epoch=self.epoch,
                )
                trio.run(mon.run)
            except KeyboardInterrupt:
                return

    def reader(self) -> Tuple[Optional[Reader], Optional[Path]]:
        test_files = RIB_FILES.copy()
        if self.replay:
            test_files.update(REPLAY_FILES)

        d = self.deployment.current()
        if not d:
            return None, None

        if self.servers is not None:
            server_count = self.servers
        else:
            server_count = d.server_count
        if self.clients is not None:
            client_count = self.clients
        else:
            client_count = d.client_count

        if d.name == "bastion":
            log_path = Path.home()
            reader_class = BastionReader
        else:
            log_path = d.log_path()
            reader_class = DirectoryReader
            if not log_path.exists():
                return None, None

        return reader_class(
            log_path,
            test_files,
            node_pattern=RIB_DIR_PATTERN,
            max_clients=client_count,
            max_servers=server_count
        ), log_path / ".restart_monitor"

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument(
            "--replay", action="store_true", help="Parse replay/receive.log files and report on package delivery."
        )
        parser.add_argument(
            "--debug", action="store_true", help="Run the monitor in debug mode."
        )
        parser.add_argument("--clients", type=int, help="Number of clients to monitor.")
        parser.add_argument("--servers", type=int, help="Number of clients to monitor.")
        parser.add_argument("--epoch", default="genesis", help="Only display information pertinent to this epoch.")
