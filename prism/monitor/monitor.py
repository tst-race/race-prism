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
from pathlib import Path

import trio

from prism.monitor.reader import LogLine, Reader
from prism.monitor.report import Deployment, PrintReporter


class Monitor:
    """The main class. Orchestrates subtasks for reading and processing log lines."""

    def __init__(
            self,
            reader: Reader,
            interval: float = 2.0,
            replay: bool = False,
            debug: bool = False,
            verbose: bool = False,
            clear_file: Path = None,
            epoch: str = "genesis",
    ):
        self.reader = reader
        self.interval = interval
        self.replay = replay
        self.debug = debug
        self.verbose = verbose
        self.clear_file = clear_file

        self.deployment = Deployment(reader_stats=self.reader.stats, epoch=epoch)

        if not self.replay:
            self.deployment.replay = None

    async def run(self):
        line_in, line_out = trio.open_memory_channel(0)
        reporter = PrintReporter(
            self.deployment, interval=self.interval, clear=not self.debug, verbose=self.verbose
        )

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.reader.run, line_in)
            nursery.start_soon(self.dispatch, line_out)
            nursery.start_soon(reporter.run)
            if self.clear_file:
                nursery.start_soon(self.check_restart, self.clear_file, nursery.cancel_scope)

    async def dispatch(self, line_out: trio.MemoryReceiveChannel):
        """Pulls log lines from the reader and dispatches them to appropriate handlers."""

        line: LogLine
        async for line in line_out:
            if line.file_type == "replay":
                self.deployment.replay.parse(line)
            elif line.node_type == "client":
                if line.node_name not in self.deployment.clients:
                    self.deployment.add_client(line.node_name)
                self.deployment.clients[line.node_name].parse(line)
            elif line.node_type == "server":
                if line.node_name not in self.deployment.servers:
                    self.deployment.add_server(line.node_name)
                self.deployment.servers[line.node_name].parse(line)

    async def check_restart(self, clear_file: Path, cancel_scope: trio.CancelScope):
        """Watches a file and signals the monitor to clear its data and restart
        when that file is created or touched."""

        async def get_time():
            if not clear_file.exists():
                return 0
            else:
                return clear_file.stat().st_mtime

        base_time = await get_time()

        while True:
            new_time = await get_time()
            if new_time > base_time:
                cancel_scope.cancel()

            await trio.sleep(0.2)
