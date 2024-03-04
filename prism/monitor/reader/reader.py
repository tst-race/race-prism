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
from dataclasses import dataclass, field

import trio


@dataclass
class ReaderStats:
    lines_read: int = field(default=0)


class Reader:
    """Common superclass/interface for readers."""

    def __init__(self):
        self.stats = ReaderStats()

    async def run(self, line_in: trio.MemorySendChannel):
        pass
