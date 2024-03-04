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

from ..command import RIBCommand
from prism.ribtools.commands.aws_commands import command_table
from ..args import add_subcommands


class AWS(RIBCommand):
    """AWS-related commands"""

    aws_command: str = None

    def run(self):
        command = command_table.get(self.aws_command)(**self._args)
        command.pre_run()
        command.run()
        command.post_run()

    def pre_run(self):
        pass

    def post_run(self):
        pass

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        add_subcommands(parser, "aws_command", command_table)
