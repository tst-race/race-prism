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
from prism.ribtools.error import PRTError

from ...command import Command


class Use(Command):
    """Make an aws env the current active env."""

    name: str = None

    def run(self):
        e = AWSEnvironment.load_named(self.name)
        if not e:
            raise PRTError(f"Could not find env named {self.name}.")
        e.make_current()

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("name", metavar="NAME", help="The name of the environment to activate.")
