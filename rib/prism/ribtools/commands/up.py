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
from .aws_commands.setup_bastion import SetupBastion
from ..command import RIBCommand
from ..deployment import DeploymentMode


class Up(RIBCommand):
    """Bring the active deployment up."""

    def run(self):
        d = self.ensure_current()
        cmd = self.deployment_boilerplate(d, "up")
        result = self.subprocess(cmd)

        if d.mode == DeploymentMode.aws and result.returncode == 0:
            SetupBastion().run()
