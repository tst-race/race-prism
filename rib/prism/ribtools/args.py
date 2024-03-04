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
import importlib
import inspect
import pkgutil
from typing import Dict, Type, Callable, Iterable

from prism.ribtools.command import Command, ExternalCommand
from prism.ribtools.environment import is_rib


def add_subcommands(parser: argparse.ArgumentParser, dest: str, command_table: Dict[str, Type[Command]]):
    commands = parser.add_subparsers(dest=dest)
    added = []

    for subcommand in command_table.values():
        if subcommand in added:
            continue

        sub = commands.add_parser(
            subcommand.command_name(),
            aliases=subcommand.aliases,
            help=subcommand.help(),
            description=subcommand.description(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

        subcommand.extend_parser(sub)
        sub.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="Print verbose output, including what commands prt invokes on your behalf.",
        )
        sub.add_argument(
            "--ci-run",
            action="store_true",
            help="Skip some checks for limited CI build capabilities.",
        )
        added.append(subcommand)


def find_subcommands(
    path: Iterable[str], package: str, predicate: Callable[[Type[Command]], bool] = None
) -> Dict[str, Type[Command]]:
    command_table: Dict[str, Type[Command]] = {}

    for module in pkgutil.iter_modules(path):
        m = importlib.import_module(f".{module.name}", package=package)
        for (_, c) in inspect.getmembers(m, inspect.isclass):
            if issubclass(c, Command) and c.__module__ != Command.__module__:
                if predicate and not predicate(c):
                    continue
                if issubclass(c, ExternalCommand) and is_rib:
                    continue
                if c.command_name() in command_table:
                    continue
                command_table[c.command_name()] = c
                for alias in c.aliases:
                    command_table[alias] = c

    return command_table
