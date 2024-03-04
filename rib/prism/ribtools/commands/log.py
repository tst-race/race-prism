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
from pathlib import Path
from typing import List, Optional

from prism.ribtools.error import PRTError
from prism.ribtools.name import race_name, shorthand_regex

from ..command import ExternalCommand
from ..deployment import Deployment


scope_names = {
    "c": "client",
    "s": "server",
    "g": "global",
}
empty_suffix_files = {
    "client": "prism/prism.log",
    "server": "prism/prism.log",
    "global": "*",
}
suffix_log = {
    "r": "race.log",
    "rp": "prism/replay.log",
    "rc": "prism/receive.log",
    "m": "prism/prism.server.monitor.log",
    "mpc": "prism/mpc.log",
    "cm": "prism/prism.client.monitor.log",
    "err": "racetestapp.stderr.log",
    "out": "racetestapp.stdout.log",
    "tst": "racetestapp.log",
}
suffix_config = {"c": "committees", "p": "personas", "l": "link-profiles", "n": "neighborhood"}

# -f force binary files to be open, to support colors
# -R smarter raw input for less buggy color parsing?
# -Q suppress errors/bells
# -S don't wrap lines
# -K quit on interrupt -- prevents terminal getting stuck after Ctrl-C
less_options = "-fRQSK"
# candidates:
# -J display status column
# -m show % of file on prompt
# -N show line numbers
# -P custom prompt


def filter_command(filter_spec: str, color=True) -> str:
    color_flag = "--color=always" if color else ""
    if filter_spec.startswith("!"):
        return f'grep -v "{filter_spec[1:]}"'
    else:
        return f'grep {color_flag} "{filter_spec}"'


class Log(ExternalCommand):
    """View or compress log files.

    By default, opens the file with less -fr. With the -f/--follow flag, runs
    tail -f instead.

    The shorthand syntax has 3 components.

    First, a node type:
        c: client
        s: server
        g: global (clients + servers)

    Second, an optional node number.

    Finally, an optional suffix that indicates the particular file of interest.
    With no suffix, prt log will view prism-client.log or prism-server.log.out
    as appropriate for the node type.

    Suffixes:
        r: race.log
        rp: replay.log
        rc: receive.log
        m: prism-server.monitor.log
        err: racetestapp.stderr.log
        out: racetestapp.stdout.log
        tst: racetestapp.log

        c: committee json
        p: persona json

    Examples:
        c1 -> race-client-00001's prism-client.log
        s -> all servers' prism-server.log.out files
        s5rc -> race-server-00005's receive.log
        sp -> the common server.json persona
        c1c -> race-client-00001's committee file
        gerr -> all racetestapp.stderr.log files

    You may also include any number of filters, which will be treated as grep
    arguments. A filter that begins with ! will be removed from the stream.

    If invoked with -z/--zip, instead of examining a particular log, compress
    the active deployment's logs directory into the specified file."""

    aws_forward = True

    follow: bool = False
    list_files: bool = False
    shorthand: str = None
    filters: List[str] = None
    zip_file: str = None

    def run(self):
        d = self.ensure_current()
        if self.zip_file:
            self.zip(d, Path(self.zip_file))
            return

        target_files = self.expand_shorthand(self.shorthand)

        if self.list_files:
            self.print_files(target_files)
            return

        filter_commands = list(map(filter_command, self.filters))
        if self.follow:
            self.tail(target_files, filter_commands)
        else:
            self.less(target_files, filter_commands)

    def zip(self, deployment: Deployment, zip_file: Path):
        cmd = ["zip", "-r", zip_file, "logs", "-x", "opentracing", ".restart_monitor"]
        self.subprocess(cmd, cwd=deployment.log_path().parent)

    def print_files(self, target_files: List[Path]):
        for file in target_files:
            print(file)

    def tail(self, target_files: List[Path], filter_commands: List[str]):
        cmd = " | ".join([f"tail -F {' '.join(str(f) for f in target_files)}", *filter_commands])
        self.subprocess([cmd], shell=True)

    def less(self, target_files: List[Path], filter_commands: List[str]):
        deployment_path = self.ensure_current().path()
        target_files = [file.relative_to(deployment_path) for file in target_files if file.exists()]
        if not target_files:
            raise PRTError("No matching files found.")

        cmd = " | ".join(
            [f"grep \"\" {' '.join(str(f) for f in target_files)}", *filter_commands, f"less {less_options}"]
        )
        self.subprocess([cmd], shell=True, cwd=self.ensure_current().path())

    def expand_shorthand(self, shorthand) -> List[Path]:
        components = self.parse_shorthand(shorthand)
        return self._expand_shorthand(**components)

    def parse_shorthand(self, shorthand) -> dict:
        match = shorthand_regex.match(shorthand)
        if not match:
            raise PRTError(f"Invalid shorthand: {shorthand}")

        d = match.groupdict()

        scope = scope_names[d["scope"]]
        suffix = d["suffix"]
        node_num = int(d["node_num"]) if d["node_num"] else 0
        node_name = race_name(scope, node_num) if scope != "global" and node_num else None

        return {"scope": scope, "suffix": suffix, "node_name": node_name}

    def _expand_shorthand(self, scope: str, suffix: str, node_name: Optional[str] = None) -> List[Path]:
        if not suffix or suffix in suffix_log:
            return self.expand_log(scope, suffix, node_name)
        elif suffix in suffix_config:
            return self.expand_config(scope, suffix, node_name)
        else:
            raise PRTError(f"Unknown suffix {suffix}.")

    def expand_log(self, scope, suffix, node_name) -> List[Path]:
        if not suffix:
            file_name = empty_suffix_files[scope]
        else:
            file_name = suffix_log[suffix]

        log_path = self.ensure_current().log_path()
        if scope == "global":
            return list(log_path.glob(f"*/{file_name}"))
        else:
            if node_name:
                return [log_path / node_name / file_name]
            else:
                return list(log_path.glob(f"race-{scope}*/{file_name}"))

    def expand_config(self, scope: str, suffix: str, node_name: Optional[str]):
        config_path = self.ensure_current().config_path()
        if suffix == "c" and (scope == "global" or not node_name):
            raise PRTError("Committees are node-specific.")

        if scope == "global":
            return [config_path / "race-server-00001" / "prism.json"]
        elif node_name is None:
            return [config_path / f"race-{scope}-00001" / f"{scope}.json"]
        elif suffix == "c":
            return [config_path / node_name / "committee.json"]
        elif suffix == "n":
            return [config_path / node_name / "neighborhood.json"]
        elif suffix == "l":
            return [config_path / node_name / "link-profiles.json"]
        else:
            return [config_path / node_name / f"{node_name}.json"]

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("-f", "--follow", action="store_true", help="Run tail -F instead of less -fr.")
        parser.add_argument("-l", "--list-files", action="store_true", help="List files matching shorthand and exit.")
        parser.add_argument(
            "shorthand", metavar="SHORTHAND", nargs="?", help="The file to look up in shorthand notation."
        )
        parser.add_argument(
            "filters", metavar="[!]FILTER", help="Strings to grep for (prepend ! for grep -v).", nargs="*"
        )
        parser.add_argument(
            "-z", "--zip", dest="zip_file", metavar="ZIP_FILE", help="A file to zip the logs directory into."
        )
