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

from prism.ribtools.deployment import Deployment
from prism.ribtools.environment import environment
from prism.ribtools.error import PRTError
from ..command import RIBCommand


class Remove(RIBCommand):
    """Remove a deployment from RIB."""

    aliases = ["rm"]

    name: str = None
    purge: bool = False

    def run(self):
        if self.name:
            d = Deployment.load_named(self.name)
            if not d:
                raise PRTError(f"Could not find info about deployment {self.name}.")
        else:
            d = self.ensure_current()

        if d.path().exists():
            cmd = self.deployment_boilerplate(d, "remove")

            self.subprocess(cmd)
        elif not self.purge:
            raise PRTError(f"Deployment {d.name} does not exist in RIB.")

        if self.purge:
            Deployment.storage_path(d.name).unlink()
            if d.is_current():
                environment.current_deployment_path.unlink()

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("name", metavar="NAME", nargs="?", help="The deployment to remove (defaults to active).")
        parser.add_argument("-p", "--purge", action="store_true", help="Also remove the deployment from PRT.")
