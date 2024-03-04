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

from ..command import RIBCommand


class Configure(RIBCommand):
    """Run config generation for active deployment."""

    aliases = ["co", "conf"]

    verbose: bool = False
    dry_run: bool = False

    def run(self):
        d = self.ensure_current()

        cmd = [*self.deployment_boilerplate(d, "config", "generate"), "--force"]
        if self.verbose:
            cmd.append("-v")

        for k, v in d.comms_custom_dir.items():
            comms_dict = {k: v}
            cmd.extend([fr"--comms-custom-args={json.dumps(comms_dict, separators=(',', ':'))}"])

        if d.custom_args:
            cmd.extend(["--network-manager-custom-args", " ".join(d.custom_args)])

        if self.dry_run:
            if d.custom_args:
                cmd[-1] = f'"{cmd[-1]}"'
            print(" ".join(cmd))
            return

        self.subprocess(cmd)
        self.fix_permissions()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument(
            "-n", "--dry-run", action="store_true", help="Don't configure the deployment, just print the RIB command."
        )
