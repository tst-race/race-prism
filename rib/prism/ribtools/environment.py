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
import os
import pwd
import socket
import sys
from pathlib import Path
from typing import Optional


is_bastion = "bastion" in socket.gethostname()
is_rib = os.getenv("RIB_VERSION") is not None


class PRTEnv:
    @property
    def prism_rib_home(self) -> Optional[Path]:
        return None

    @property
    def race_version(self) -> Optional[str]:
        race_version_path = self.prism_rib_home / "RACE_VERSION"
        if race_version_path.exists():
            return race_version_path.read_text().strip()

    @property
    def rib_version(self):
        rib_version_path = self.prism_rib_home / "RIB_VERSION"
        if rib_version_path.exists():
            return rib_version_path.read_text().strip()
        else:
            return self.race_version

    @property
    def repo_home(self) -> Path:
        from prism.cli.repo import REPO_ROOT
        return REPO_ROOT

    @property
    def rib_dir(self) -> Optional[Path]:
        p = Path.home() / ".race" / "rib"
        if p.exists():
            return p

    @property
    def prt_dir(self) -> Optional[Path]:
        return self.rib_dir / "prism-rib-tools"

    @property
    def current_deployment_path(self) -> Path:
        return self.prt_dir / "CURRENT"

    @property
    def deployments_dir(self) -> Path:
        return self.prt_dir / "deployments"

    @property
    def current_environment_path(self) -> Path:
        return self.prt_dir / "CURRENT-AWS-ENV"

    @property
    def environments_dir(self) -> Path:
        return self.prt_dir / "environments"

    @property
    def bastion_ip_path(self) -> Path:
        return self.prt_dir / "BASTION_IP"

    @property
    def elasticsearch_ip_path(self) -> Path:
        return self.prt_dir / "ES_IP"

    @property
    def last_started(self) -> Path:
        return self.prt_dir / "LAST_STARTED"

    def check(self):
        pass


class LocalEnv(PRTEnv):
    @property
    def prism_rib_home(self) -> Path:
        return self.repo_home / "rib"

    def check(self):
        super().check()

        if not (self.repo_home / ".git").exists():
            print("prt local env requires being run from the prism-dev repository")
            sys.exit(1)

        if os.access(self.rib_dir / ".test", os.W_OK):
            print(f"{self.rib_dir.absolute()} must be writable for prt to function.")
            print("Please execute:")
            print(f"    sudo chown -R {pwd.getpwuid(os.getuid()).pw_name} {self.rib_dir}")
            print("and try again.")
            sys.exit(1)


class RIBEnv(PRTEnv):
    @property
    def prism_rib_home(self) -> Optional[Path]:
        return Path("/code")


class BastionEnv(PRTEnv):
    @property
    def race_version(self) -> Optional[str]:
        return "bastion"

    def check(self):
        pass


environment: PRTEnv
if is_rib:
    environment = RIBEnv()
elif is_bastion:
    environment = BastionEnv()
else:
    environment = LocalEnv()
