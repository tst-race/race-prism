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

from prism.ribtools.aws_environment import AWSEnvironment
from prism.ribtools.environment import environment
from prism.ribtools.error import PRTError

from ...command import RIBCommand


class Remove(RIBCommand):
    """Remove a deployment from RIB."""

    aliases = ["rm"]

    name: str = None
    purge: bool = False

    def run(self):
        if self.name:
            e = AWSEnvironment.load_named(self.name)
            if not e:
                raise PRTError(f"Could not find info about environment {self.name}.")
        else:
            e = self.ensure_aws()

        if e.path().exists():
            cmd = self.environment_boilerplate(e, "remove")

            self.subprocess(cmd)
        elif not self.purge:
            raise PRTError(f"AWSEnvironment {e.name} does not exist in RIB.")

        if self.purge:
            AWSEnvironment.storage_path(e.name).unlink()
            if e.is_current():
                environment.current_environment_path.unlink()

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("name", metavar="NAME", nargs="?", help="The environment to remove (defaults to active).")
        parser.add_argument("-p", "--purge", action="store_true", help="Also remove the environment from PRT.")
