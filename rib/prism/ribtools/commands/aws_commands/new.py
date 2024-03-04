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
from prism.ribtools.aws_environment import AWSEnvironment
from prism.ribtools.error import PRTError

from ...command import RIBCommand


class New(RIBCommand):
    """Create and activate a new deployment."""

    aliases = ["n"]

    name: str = None
    size: int = None

    def pre_run(self):
        super().pre_run()
        if AWSEnvironment.exists(self.name):
            raise PRTError(f"AWSEnvironment {self.name} already exists.")

    def run(self):
        e = AWSEnvironment(self.name, linux_instance_count=self.size)
        e.save()
        e.make_current()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument(
            "--size",
            metavar="INSTANCES",
            default=4,
            type=int,
            help="The number of Linux node instances (default 4)",
        )
        parser.add_argument("name", metavar="NAME", help="The name of the new environment.")
