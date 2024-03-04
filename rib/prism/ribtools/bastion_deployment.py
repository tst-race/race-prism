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
from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from prism.ribtools.deployment import Deployment, DeploymentMode
from prism.ribtools.error import PRTError


@dataclass
class BastionDeployment(Deployment):
    def path(self) -> Path:
        return self.bastion_home()

    def log_path(self) -> Path:
        return bastion_log_path

    def config_path(self) -> Path:
        return self.path() / "data" / "network-manager" / "prism"

    def save(self, save_path: Optional[Path] = None):
        raise PRTError("Can't save BastionDeployment")

    def is_current(self) -> bool:
        return True

    def make_current(self):
        return True

    def is_created(self) -> bool:
        return True

    @classmethod
    def bastion_home(cls) -> Path:
        if "rib" in socket.gethostname():
            return Path.home()
        else:
            return Path("/home/twosix")

    @staticmethod
    def current() -> Optional[Deployment]:
        return BastionDeployment(
            name="bastion",
            mode=DeploymentMode.bastion,
            overrides={},
            client_count=count_nodes("client"),
            server_count=count_nodes("server"),
            range_file=None,
            comms_channels=[],
        )


bastion_log_path = BastionDeployment.bastion_home() / "logs"


def count_nodes(node_type: str) -> int:
    return int(os.getenv(f"PRT_{node_type.upper()}_COUNT", len(list(bastion_log_path.glob(f"race-{node_type}-*")))))
