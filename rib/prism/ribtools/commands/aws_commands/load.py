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

from prism.ribtools.aws_environment import AWSEnvironment
from prism.ribtools.error import PRTError

from ...command import RIBCommand


class Load(RIBCommand):
    """Load an environment from a file."""

    name: str = None
    filename: str = None

    def run(self):
        load_path = Path(self.filename)
        e = AWSEnvironment.load_path(load_path)
        if not e:
            raise PRTError(f"Could not load deployment from {load_path}.")

        if self.name:
            e.name = self.name

        if AWSEnvironment.exists(e.name):
            raise PRTError(f"AWSEnvironment {e.name} already exists.")

        e.save()
        e.make_current()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument("--name", metavar="NAME", help="Name the loaded environment NAME.")
        parser.add_argument("filename", metavar="FILE", help="The file to load the environment from.")
