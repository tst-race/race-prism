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
import shutil
import tempfile
from argparse import ArgumentParser
from pathlib import Path

from prism.ribtools.command import ExternalCommand
from prism.ribtools.environment import environment
from prism.ribtools.error import PRTError


class SetupBastion(ExternalCommand):
    """Copy prt to bastion and ensure it can be invoked with "prt"."""

    host: str = None
    user: str = None
    identity_file: str = None

    def run(self):
        archive_name = "prt.tgz"
        script_path = Path(__file__).parent / "setup_prt.sh"

        with tempfile.TemporaryDirectory() as td:
            prt_paths = [
                environment.prism_rib_home / "prism" / "ribtools",
                environment.repo_home / "prism" / "common",
                environment.repo_home / "prism" / "monitor",
                environment.repo_home / "prism" / "cli",
            ]

            base_path = Path(td)
            tools_path = base_path / "tools"
            prism_path = tools_path / "prism"
            prism_path.mkdir(parents=True)

            for path in prt_paths:
                shutil.copytree(path, prism_path / path.name)

            shutil.copytree(environment.prism_rib_home / "bin", tools_path / "bin")
            shutil.copy(environment.prism_rib_home / "setup.py", tools_path)

            result = self.upload_archive(
                tools_path,
                archive_name,
                identity_file=self.identity_file,
                user=self.user,
                host=self.host,
                extras=[script_path],
            )
            if result.returncode:
                raise PRTError(f"Failed to upload PRT to Bastion:\n{result.stderr.decode('utf-8')}.")

        setup_command = ["ssh", "bash", "setup_prt.sh"]

        if not self.host:
            self.ensure_aws()
            d = self.ensure_current()
            setup_command.extend([str(d.client_count), str(d.server_count)])

        result = self.ssh(setup_command, user=self.user, host=self.host, identity_file=self.identity_file)
        if result.returncode:
            raise PRTError(f"Setup PRT failed:\n{result.stderr.decode('utf-8')}")

        # write current Bastion and Elasticsearch IPs to file (e.g., for ES Dashboard)
        e = self.ensure_aws()
        environment.bastion_ip_path.write_text(f"{e.bastion_ip()}")
        environment.elasticsearch_ip_path.write_text(f"{e.bastion_ip('cluster-manager')}")

    @classmethod
    def command_name(cls) -> str:
        return "setup-bastion"

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("--host", default="", help="The hostname or IP address for Bastion.")
        parser.add_argument("--user", default="sri-network-manager", help="The user to log in as.")
        parser.add_argument("--identity", dest="identity_file", help="An SSH identity file to use.")
