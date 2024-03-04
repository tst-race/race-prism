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

from prism.ribtools.deployment import Deployment
from prism.ribtools.error import PRTError

from ..command import RIBCommand


class Load(RIBCommand):
    """Load a deployment from a file."""

    aliases = ["l", "lg"]

    force: bool = False
    name: str = None
    filename: str = None

    def run(self):
        load_path = Path(self.filename)
        d = Deployment.load_path(load_path)
        if not d:
            raise PRTError(f"Could not load deployment from {load_path}.")

        if self.name:
            d.name = self.name

        if Deployment.exists(d.name) and not self.force:
            raise PRTError(f"Deployment {d.name} already exists. Use --force to overwrite.")

        d.save()
        d.make_current()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument(
            "-f", "--force", action="store_true", help="Overwrite existing deployment of the same name."
        )
        parser.add_argument("--name", metavar="NAME", help="Name the loaded deployment NAME.")
        parser.add_argument("filename", metavar="FILE", help="The file to load the deployment from.")
