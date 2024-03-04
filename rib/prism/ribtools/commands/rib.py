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
from argparse import ArgumentParser
from pathlib import Path

from ..command import ExternalCommand
from ..environment import environment
from ..error import PRTError

RIB_REMOTE_URL = "git@github.com:tst-race/race-in-the-box.git"


class RIB(ExternalCommand):
    """Run a race-in-the-box container or connect to an existing container."""

    ssh_key = None
    rib_version = None
    rib_branch = None
    rib_entrypoint = None
    sub_command = None

    def run(self):
        if not environment.prism_rib_home.exists():
            raise PRTError("Could not find prism-dev/rib directory.")

        if self.sub_command:
            if not self.rib_running():
                raise PRTError("Executing commands through prt rib requires running RIB.")
            self.rib_process(self.sub_command, capture_output=False)
            return

        if self.rib_running():
            self.rib_connect()
        else:
            self.rib_update()
            self.rib_run()

    def rib_connect(self):
        self.rib_process(["/bin/bash"], capture_output=False)

    @property
    def rib_path(self) -> Path:
        return environment.prism_rib_home / "race-in-the-box"

    def git(self, *args, cwd=None):
        if not cwd:
            cwd = self.rib_path
        self.subprocess(["git", *args], cwd=cwd, capture_output=False)

    def rib_update(self):
        if not self.rib_path.exists():
            self.rib_install()
            return

        print("Updating race-in-the-box")
        self.git("fetch")
        self.checkout_rib()

    def checkout_rib(self):
        self.git("checkout", self.rib_branch)
        self.git("pull")

    def rib_install(self):
        print("Installing race-in-the-box")
        self.git("clone", RIB_REMOTE_URL, "race-in-the-box", cwd=environment.prism_rib_home)

    def rib_run(self):
        rib_path = environment.prism_rib_home / "race-in-the-box"
        rib_version = self.rib_version or environment.rib_version

        if self.rib_entrypoint:
            entry_point = rib_path / "entrypoints" / self.rib_entrypoint
        else:
            entry_point = rib_path / "entrypoints" / f"rib_{rib_version}.sh"

        if not entry_point.exists():
            raise PRTError(f"Could not find RIB entrypoint {entry_point}")

        cmd = [
            entry_point,
            "--code", environment.prism_rib_home,
            "--version", rib_version,
        ]

        ssh_key_path = Path(self.ssh_key)
        if not ssh_key_path.exists():
            raise print(f"WARNING: Could not find SSH key at {self.ssh_key}. AWS/T&E commands will break.")
        else:
            cmd.extend(["--ssh", ssh_key_path])

        self.subprocess(cmd, capture_output=False)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        default_ssh_path = Path.home() / ".ssh" / "sri_prism_rangekey"

        parser.add_argument(
            "--ssh-key",
            metavar="KEYFILE",
            default=str(default_ssh_path),
            help=f"The path to the PRISM ssh key. Defaults to {default_ssh_path}"
        )

        parser.add_argument(
            "--rib",
            dest="rib_version",
            metavar="RIB_VERSION",
            help="Override the version of RIB used. Must correspond to a file called rib_[RACE_VERSION].sh "
                 "in race-in-the-box/entrypoints"
        )

        parser.add_argument(
            "--entrypoint",
            dest="rib_entrypoint",
            metavar="RIB_ENTRYPOINT",
            help="The entry point to use. By default, it is rib_{RIB_VERSION}.sh"
        )

        parser.add_argument(
            "--branch",
            metavar="RIB_BRANCH",
            dest="rib_branch",
            default="master",
            help="Pick a branch of the RIB repository.",
        )

        parser.add_argument(
            metavar="COMMAND",
            dest="sub_command",
            nargs="*",
            help="A command to pass through to an already-running RIB instance."
        )
