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

from prism.ribtools.environment import environment
from ..build import Build

from ...command import ExternalCommand
from ...error import PRTError


class Hotfix(ExternalCommand):
    """Build a hotfix release, compress it, and upload to Bastion."""

    host: str = None
    user: str = None
    identity_file: str = None

    def run(self):
        self.ensure_aws()
        Build().run()
        result = self.upload_archive(
            environment.prism_rib_home / "release",
            "release.tgz",
            identity_file=self.identity_file,
            user=self.user,
            host=self.host,
        )

        if result.returncode:
            raise PRTError(f"Failed to upload hotfix to Bastion:\n{result.stderr.decode('utf-8')}")

        self.ssh(
            ["ssh", "-t", "bash", "-ic", '"prt hotfix"'],
            capture_output=False,
            identity_file=self.identity_file,
            user=self.user,
            host=self.host,
        )

        if result.returncode:
            raise PRTError(f"Hotfix failed:\n{result.stderr.decode('utf-8')}")

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("--host", default="", help="The hostname or IP address for Bastion.")
        parser.add_argument("--user", default="sri-network-manager", help="The user to log in as.")
        parser.add_argument("--identity", dest="identity_file", help="An SSH identity file to use.")
