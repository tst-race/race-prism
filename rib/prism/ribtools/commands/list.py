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
from prism.ribtools.deployment import Deployment
from prism.ribtools.environment import environment

from ..command import RIBCommand


class List(RIBCommand):
    """List all prt deployment configs."""

    aliases = ["ls"]

    def run(self):
        current = Deployment.current()
        deployments = sorted([p.stem for p in environment.deployments_dir.glob("*.json")])

        for deployment in deployments:
            if current and deployment == current.name:
                print(f"* {deployment}")
            else:
                print(f"  {deployment}")
