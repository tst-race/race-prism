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
from typing import List

import requests
from requests.exceptions import ConnectionError

from ..command import RIBCommand


class Clean(RIBCommand):
    """Truncate the log files of the active deployment."""

    aliases = ["cl"]
    aws_forward = True

    def run(self):
        d = self.ensure_current()

        for log_dir in d.log_path().glob("race-*"):
            if not log_dir.is_dir():
                continue
            files = [log_file for log_file in log_dir.iterdir() if log_file.is_file()]
            prism_dir = log_dir / "prism"
            if prism_dir.is_dir():
                files += [log_file for log_file in prism_dir.iterdir() if log_file.is_file()]
            self.truncate_path(log_dir, files)

        # Restart monitor
        self.restart_monitor()

        self.clean_whiteboard()

    def restart_monitor(self):
        (self.deployment.log_path() / ".restart_monitor").touch()

    def clean_whiteboard(self):
        # Clear TwoSix whiteboard if available
        if "twoSixIndirectCpp" in self.deployment.comms_channels:
            try:
                requests.get("http://localhost:5000/resize/0")
            except ConnectionError:
                pass

    def truncate_path(self, log_dir: Path, log_files: List[Path]):
        self.subprocess([*("truncate -s 0".split()), *log_files], capture_output=True)
