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
import argparse
import sys

from prism.ribtools.args import add_subcommands
from prism.ribtools.error import PRTError
from prism.ribtools.environment import environment, is_bastion
from prism.ribtools.first_run import first_run_setup

if is_bastion:
    from prism.ribtools.commands.bastion import command_table as bastion_command_table

    command_table = bastion_command_table
else:
    from prism.ribtools.commands import command_table as local_command_table

    command_table = local_command_table

parser = argparse.ArgumentParser(prog="prt", description=f"PRISM RIB Toolkit (RACE {environment.race_version})")
add_subcommands(parser, "command", command_table)
args = parser.parse_args()

if not args.command:
    parser.print_help()
    sys.exit(0)

try:
    from .deployment import DeploymentMode

    if not args.ci_run:
        first_run_setup()

    command_class = command_table[args.command]
    print(f'args.ci_run={args.ci_run}')
    command = command_class(**vars(args))
    if command.aws_forward and command.ensure_current().mode == DeploymentMode.aws:
        command.ssh_forward()
    else:
        command.pre_run()
        command.run()
        command.post_run()
except PRTError as e:
    print(e)
    sys.exit(1)
except KeyboardInterrupt:
    pass
