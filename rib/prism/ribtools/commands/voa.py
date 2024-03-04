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
import json
from pathlib import Path

from prism.ribtools.environment import environment
from ..command import RIBCommand


class Delay(RIBCommand):
    """Run `voa apply <JSON>` command for delaying packages by given seconds to channel."""

    channel: str = "twoSixIndirectCpp"
    delay: float = 10.0
    jitter: bool = False

    def run(self):
        d = self.ensure_current()

        cmd = self.deployment_boilerplate(d, "voa", "apply")
        # create configuration file under .race:
        param = "jitter" if self.jitter else "holdtime"
        json_path = Path.joinpath(d.path(), f"delay-{self.channel}.json")
        container_path = "/root" / Path(*list(json_path.parts)[len(Path.home().parts):])
        with open(json_path, "w") as fp:
            json.dump({
                "0001" : {
                    "tag": f"voa-delay-{param}",
                    "action": "delay",
                    "params": { param: f"{self.delay:.1f}" },
                    "startupdelay": "0",
                    "to": {
                        "type": "channel",
                        "matchid": self.channel
                    }
                }
            }, fp, indent=2)
        cmd.extend(["--conf-file", str(container_path)])
        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("-c", "--channel", default="twoSixIndirectCpp",
                            help=f"Which channel to apply delay to (default: {cls.channel})")
        parser.add_argument("-d", "--delay", type=float, required=True,
                            help="Seconds of delay to add to all communication on channel")
        parser.add_argument("-j", "--jitter", default=False, action="store_true",
                            help="Whether to use random jitter rather than static (default) for delays")
