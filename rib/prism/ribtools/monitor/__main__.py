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
import time
from pathlib import Path

import trio

from prism.monitor import Monitor, DirectoryReader

from .bastion import BastionReader
from .files import RIB_DIR_PATTERN, RIB_FILES, REPLAY_FILES

parser = argparse.ArgumentParser("prism.monitor")
parser.add_argument("--clients", type=int, default=0, help="The number of clients to monitor. By default, 0 for Bastion and all for local.")
parser.add_argument("--servers", type=int, default=0, help="The number of servers to monitor. By default, 0 for Bastion and all for local.")
parser.add_argument("--epoch", default="genesis", help="Only display information pertinent to this epoch.")
parser.add_argument("--replay", action="store_true", help="Monitor information about Comms channel latency and package loss.")
parser.add_argument("--verbose", action="store_true", help="More verbose output.")
parser.add_argument("deployment", help="The name of the deployment to monitor, or 'bastion' if monitoring an AWS/T&E deployment from bastion.")


def make_reader(args):
    test_files = RIB_FILES.copy()
    if args.replay:
        test_files.update(REPLAY_FILES)

    if args.deployment == "bastion":
        log_path = Path.home()
        reader_class = BastionReader
        max_clients = args.clients
        max_servers = args.servers
    else:
        log_path = Path.home() / ".race" / "rib" / "deployments" / "local" / args.deployment / "logs"
        if not log_path.exists():
            return None, None

        reader_class = DirectoryReader
        max_clients = args.clients or 10000
        max_servers = args.servers or 1000

    return reader_class(
        log_path,
        test_files,
        node_pattern=RIB_DIR_PATTERN,
        max_clients=max_clients,
        max_servers=max_servers,
    ), log_path / ".restart_monitor"


def run():
    args = parser.parse_args()

    while True:
        try:
            reader, clear_file = make_reader(args)

            if not reader:
                time.sleep(1)
                continue

            mon = Monitor(
                reader,
                replay=args.replay,
                verbose=args.verbose,
                debug=False,
                clear_file=clear_file,
                epoch=args.epoch,
            )

            trio.run(mon.run)
        except KeyboardInterrupt:
            return


run()




