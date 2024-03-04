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
import math
import re
from io import SEEK_END
from json import JSONDecodeError
from pathlib import Path
from typing import List, Dict

import trio

from .log_line import LogLine
from .reader import Reader

DIR_PATTERN = re.compile(r"(prism)-(?P<type>client|server)-(?P<number>\d+)")


class DirectoryReader(Reader):
    """Reads log files from a local filesystem."""

    def __init__(
            self,
            log_dir,
            files: Dict[str, Dict[str, str]],
            node_pattern: re.Pattern = DIR_PATTERN,
            tail: bool = False,
            max_clients: int = math.inf,
            max_servers: int = math.inf,
    ):
        super().__init__()
        self.dir = log_dir
        self.node_pattern = node_pattern
        self.files = files
        self.tail = tail
        self.max_clients = max_clients
        self.max_servers = max_servers

    def get_dirs(self) -> List[Path]:
        nodes = []

        for subdir in self.dir.iterdir():
            if not subdir.is_dir():
                continue

            match = self.node_pattern.match(subdir.name)
            if not match:
                continue

            d = match.groupdict()
            node_type = d["type"]
            node_number = int(d["number"])

            if node_type == "client":
                if self.max_clients is None or node_number <= self.max_clients:
                    nodes.append(subdir)
            elif node_type == "server":
                if self.max_servers is None or node_number <= self.max_servers:
                    nodes.append(subdir)

        return nodes

    async def run(self, line_in: trio.MemorySendChannel):
        async with trio.open_nursery() as nursery:
            for subdir in self.get_dirs():
                if "server" in subdir.name:
                    dir_type = "server"
                elif "client" in subdir.name:
                    dir_type = "client"
                else:
                    continue

                for filename, tags in self.files.items():
                    if "node_type" in tags and tags["node_type"] != dir_type:
                        continue

                    file = subdir.joinpath(filename)
                    file_tags = {
                        **tags,
                        "node": subdir.name,
                        "node_type": dir_type,
                        "file_name": filename,
                    }
                    nursery.start_soon(self.read_file, line_in.clone(), file, file_tags)

    async def read_file(self, line_in: trio.MemorySendChannel, file: Path, tags: Dict[str, str]):
        while not file.exists():
            await trio.sleep(1.0)

        async with await trio.open_file(file, "r") as f:
            if self.tail:
                await f.seek(0, SEEK_END)

            while True:
                line = await f.readline()

                if line:
                    try:
                        log_line = LogLine(line, tags)
                    except JSONDecodeError as e:
                        # Might be caused by a log cleanup suddenly truncating our input stream,
                        # in which case we can expect to be canceled during this sleep and not
                        # worry about the exception.
                        await trio.sleep(1.0)
                        raise e

                    self.stats.lines_read += 1
                    await line_in.send(log_line)
                else:
                    await trio.sleep(0.1)
