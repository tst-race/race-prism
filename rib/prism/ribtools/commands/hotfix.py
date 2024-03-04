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

from .build import Build
from ..command import ExternalCommand
from ..deployment import DeploymentMode
from ..error import PRTError


class Hotfix(ExternalCommand):
    """Hotfix the latest source changes into running containers."""

    aliases = ["hf"]

    def run(self):
        d = self.ensure_current()
        if not d.is_created():
            raise PRTError(f"Deployment {d.name} has not been created yet.")

        # if d.mode == DeploymentMode.aws:
        #     self.aws_hotfix()
        # else:
        self.local_hotfix()

    def local_hotfix(self):
        d = self.ensure_current()

        from .build import release_paths, release_path, linux_server_path, linux_client_path
        self.ensure_rib()
        Build().run()

        plugin_path = Path("/root/.race/rib/deployments") / d.mode.name / d.name / "plugins"
        config_path = plugin_path / "prism"

        self.docker_cp("race-in-the-box", release_path / "config-generator", config_path)
        for source_path in release_paths.values():
            for base_path in [linux_server_path, linux_client_path]:
                try:
                    dest_path = (
                        plugin_path / base_path.parent.name / "network-manager" / "prism" / source_path.relative_to(base_path)
                    )
                    self.docker_cp("race-in-the-box", source_path, dest_path.parent)
                except ValueError:
                    pass

    def aws_hotfix(self):
        from .aws_commands.hotfix import Hotfix as AWSHotfix
        AWSHotfix().run()

    def docker_cp(self, container: str, local_path: Path, container_path: Path):
        cmd = ["docker", "cp", local_path, f"{container}:{container_path}/"]
        self.subprocess(cmd, capture_output=True)
