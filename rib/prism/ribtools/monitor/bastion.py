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
import subprocess
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, List

import trio
from prism.monitor.reader import DirectoryReader, LogLine


class LineBuffer:
    def __init__(self):
        self.buffer: str = ""

    def receive(self, b: bytes):
        s = b.decode("utf-8")
        self.buffer += s

    def has_line(self) -> bool:
        return "\n" in self.buffer

    def get_line(self) -> str:
        chunks = self.buffer.split("\n", 1)
        self.buffer = chunks[1]
        return chunks[0]


class BastionReader(DirectoryReader):
    """Reads log files from a Race-in-the-Box deployment on Bastion."""

    def get_dirs(self) -> List[Path]:
        dirs = [Path(f"race-client-{client:05d}") for client in range(1, self.max_clients + 1)]
        dirs += [Path(f"race-server-{server:05d}") for server in range(1, self.max_servers + 1)]
        return dirs

    async def read_file(self, line_in: trio.MemorySendChannel, file: Path, tags: Dict[str, str]):
        hostname = file.parts[0]
        node_path = Path("/log") / file.relative_to(hostname)
        ssh_cmd = (
            f"ssh -o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            f"-o LogLevel=ERROR "
            f"{hostname} "
            f"tail -F -n +1 "
            f"{node_path}".split()
        )
        proc = await trio.open_process(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        buffer = LineBuffer()
        try:
            while True:
                data = await proc.stdout.receive_some()
                if not data:
                    break
                buffer.receive(data)

                while buffer.has_line():
                    try:
                        log_line = LogLine(buffer.get_line(), tags)
                        self.stats.lines_read += 1
                        await line_in.send(log_line)
                    except JSONDecodeError:
                        continue
        finally:
            proc.kill()
