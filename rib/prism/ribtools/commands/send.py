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
import json
import random
import tempfile
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
from typing import Tuple

from prism.ribtools.name import race_name
from ..command import RIBCommand
from ..environment import environment


class Send(RIBCommand):
    """Send messages between clients."""

    aliases = ["s"]

    count: int = 1
    size: int = 140
    delay: float = 1.0
    text: str = None
    sender: int = None
    receiver: int = None
    all: bool = False
    one: bool = False
    two: bool = False
    not_greater_than: int = 0
    list_messages: bool = False

    def run(self):
        if self.list_messages:
            self.show_messages()
        elif self.all and not self.not_greater_than:
            self.send_all()
        else:
            self.send_plan()

    def send_all(self):
        args = [
            "--size", str(self.size),
            "--quantity", str(self.count),
            "--period", str(int(self.delay * 1000)),
        ]

        if self.sender is not None:
            args.extend(["--sender", race_name("client", self.sender)])
        if self.receiver is not None:
            args.extend(["--recipient", race_name("client", self.receiver)])

        cmd = self.deployment_boilerplate(self.ensure_current(), "message", "send-auto", *args)
        self.subprocess(cmd)

    def send_plan(self):
        plan = self.test_plan()
        if len(plan["messages"]) == 0:
            raise RuntimeWarning("Resulting Test Plan is empty!")

        temp_path = environment.prism_rib_home / "test_plans"
        with tempfile.NamedTemporaryFile(suffix="prt-plan.json", mode="w", dir=temp_path) as f:
            file_path = Path(f.name)
            json.dump(plan, f, indent=2)
            f.flush()
            args = ["--plan-file", file_path.relative_to(environment.prism_rib_home)]
            cmd = self.deployment_boilerplate(self.ensure_current(), "message", "send-plan", *args)
            self.subprocess(cmd)

    def random_client(self, exclude: int = -1) -> int:
        d = self.ensure_current()
        endpoints = (1, d.total_clients() + 1 if self.not_greater_than == 0 else self.not_greater_than + 1)
        return random.choice(list(set(range(*endpoints)) - {exclude}))

    def get_pair(self) -> Tuple[int, int]:
        if self.sender and self.receiver:
            return self.sender, self.receiver
        elif self.sender:
            return self.sender, self.random_client(self.sender)
        elif self.receiver:
            return self.random_client(self.receiver), self.receiver
        else:
            a = self.random_client()
            b = self.random_client(a)
            return a, b

    def test_plan(self):
        sender_dict = defaultdict(lambda: defaultdict(lambda: list()))
        current_time = 0

        if self.one or self.two or self.all:  # if self.all -> self.not_greater_than is set!
            msg_dict = {"time": 0}
            if self.text:
                msg_dict["message"] = self.text
            else:
                msg_dict["size"] = self.size

            d = self.ensure_current()
            if self.all:
                # to get here, must have been called with -ngt <N>
                endpoints = (1, self.not_greater_than + 1)
                for sender_idx in range(*endpoints):
                    for receiver_idx in range(*endpoints):
                        if sender_idx != receiver_idx:
                            sender_name = race_name("client", sender_idx)
                            receiver_name = race_name("client", receiver_idx)
                            sender_dict[sender_name][receiver_name].append(msg_dict)
            else:
                for fixed_idx in \
                        range(1, d.total_clients() + 1 if self.not_greater_than == 0 else self.not_greater_than + 1):
                    if self.one:
                        sender_name = race_name("client", fixed_idx)
                        receiver_name = race_name("client", self.random_client(fixed_idx))
                    else:  # must be self.two
                        sender_name = race_name("client", self.random_client(fixed_idx))
                        receiver_name = race_name("client", fixed_idx)
                    sender_dict[sender_name][receiver_name].append(msg_dict)
            return {"messages": sender_dict}

        for message_number in range(self.count):
            sender, receiver = self.get_pair()
            sender_name = race_name("client", sender)
            receiver_name = race_name("client", receiver)

            msg_dict = {"time": current_time}
            if self.text:
                msg_dict["message"] = self.text
            else:
                msg_dict["size"] = self.size

            sender_dict[sender_name][receiver_name].append(msg_dict)
            current_time += int(self.delay * 1000)

        return {"messages": sender_dict}

    def show_messages(self):
        d = self.ensure_current()
        cmd = self.deployment_boilerplate(d, "message", "list")
        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("--count", type=int, default=1, help="How many messages to send (default %(default)s)")
        parser.add_argument("--delay", type=float, default=1.0, help="The delay in seconds when sending multiple " +
                                                                     "messages (default %(default)s)")
        parser.add_argument("--sender", type=int, help="A specific sender (as an integer client#)")
        parser.add_argument("--receiver", type=int, help="A specific receiver (as an integer client#)")
        parser.add_argument("-ngt", "--not-greater-than", type=int, default=0,
                            help="Exclude all clients greater than given number from being selected sender/receiver; " +
                                 "note that any specified --sender/--receiver can be above this number")

        group_what = parser.add_mutually_exclusive_group()
        group_what.add_argument("--size", type=int, default=140, help="Message size in bytes (default %(default)s)")
        group_what.add_argument("--text", help="A specific message to send")

        group = parser.add_mutually_exclusive_group()
        group.add_argument("-l", "--list-messages", help="Invoke RIB to list all messages sent/received.", action="store_true")
        group.add_argument("-a", "--all", help="Send between all possible pairs of clients (overrides any " +
                                               "--sender or --receiver settings)", action="store_true")
        group.add_argument("-1", "--one", help="Send exactly one message per client (overrides any " +
                                               "--sender or --receiver settings)", action="store_true")
        group.add_argument("-2", "--two", help="Receive exactly one message per client (overrides any " +
                                               "--sender or --receiver settings)", action="store_true")
