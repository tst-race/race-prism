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

import re
from typing import Dict, Optional

from prism.monitor.reader import LogLine


class Parser:
    """Encapsulates a regular expression that returns matches as a dictionary of named values."""

    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)

    def match(self, line: LogLine) -> Optional[Dict[str, str]]:
        m = self.pattern.search(line.line)

        if m:
            d = m.groupdict()
            if len(d) == 0:
                # Always include at least one value so that returned
                # dicts are truthy, even if otherwise empty.
                d["_ok"] = "True"
            return d
