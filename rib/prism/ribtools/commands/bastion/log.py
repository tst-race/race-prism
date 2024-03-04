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
from typing import List, Tuple, Optional

from prism.ribtools.command import BastionCommand
from prism.ribtools.commands.log import Log as RIBLog, filter_command, less_options
from prism.ribtools.error import PRTError


class Log(BastionCommand, RIBLog):
    def run(self):
        target_files = self.expand_shorthand(self.shorthand)

        if not target_files:
            raise PRTError("No matching files found.")

        if self.list_files:
            self.print_files(target_files)
            return

        filter_commands = list(map(filter_command, self.filters))
        hostname, target_file = self.resolve_log_path(target_files[0])

        if self.follow:
            if hostname and len(target_files) == 1:
                self.bastion_tail(hostname, target_file, filter_commands)
            else:
                self.tail(target_files, filter_commands)
        else:
            if hostname and len(target_files) == 1:
                self.bastion_less(hostname, target_file, filter_commands)
            else:
                self.less(target_files, filter_commands)

    def resolve_log_path(self, path: Path) -> Tuple[Optional[str], Path]:
        """Rewrites a log path to be an absolute path on a container, and returns a tuple of the hostname and the
        path."""
        if self.is_relative_to(path, self.deployment.log_path()):
            relative = path.relative_to(self.deployment.log_path())
            hostname = relative.parts[0]
            relative = relative.relative_to(Path(hostname))
            return hostname, (Path("/log") / relative)
        elif self.is_relative_to(path, self.deployment.config_path()):
            relative = path.relative_to(self.deployment.config_path())
            hostname = relative.parts[0]
            relative = relative.relative_to(Path(hostname))
            return hostname, (Path("/data/configs/prism") / relative)
        else:
            return None, path

    def bastion_tail(self, hostname: str, target_file: Path, filter_commands: List[str]):
        ssh_part = " ".join(self.ssh_command(hostname, ["tail", "-F", str(target_file)]))
        cmd = " | ".join([ssh_part, *filter_commands])
        self.subprocess([cmd], shell=True)

    def bastion_less(self, hostname: str, target_file: Path, filter_commands: List[str]):
        ssh_part = " ".join(self.ssh_command(hostname, ["cat", str(target_file)]))
        cmd = " | ".join([ssh_part, *filter_commands, f"less {less_options}"])
        self.subprocess([cmd], shell=True)


Log.__doc__ = RIBLog.__doc__
