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

from prism.monitor.reader.files import MONITOR_FILES, REPLAY_FILES

RIB_DIR_PATTERN = re.compile(r"race-(?P<type>client|server)-(?P<number>\d+)")

RIB_FILES = {
    **MONITOR_FILES,

    "racetestapp.log": {
        "file_type": "testapp",
        "format": "text",
        "node_type": "client",
    },
}