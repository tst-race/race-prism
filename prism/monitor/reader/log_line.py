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
import json
from typing import Dict


class LogLine:
    """Holds metadata about a line from a log file. If the log file is natively JSON, parses it."""

    def __init__(self, line: str, tags: Dict[str, str]):
        self.file_type = tags["file_type"]
        self.node_type = tags["node_type"]
        self.node_name = tags["node"]
        self.file_name = tags["file_name"]

        if tags["format"] == "json":
            try:
                self.values = json.loads(line)
            except json.decoder.JSONDecodeError:
                self.values = {}
            self.line = None
        else:
            self.line = line
            self.values = None
