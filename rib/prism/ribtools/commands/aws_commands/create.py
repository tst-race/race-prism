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
from prism.ribtools.error import PRTError

from ...command import RIBCommand


class Create(RIBCommand):
    """Instruct RIB to create the active AWS environment."""

    aliases = ["cr"]

    dry_run: bool = False

    def run(self):
        e = self.ensure_aws()
        cmd = [
            *self.environment_boilerplate(e, "create"),
            # "--race",
            # environment.race_version,
            "--ssh-key-name",
            e.ssh_key,
            "--linux-x86_64-instance-count",
            e.linux_instance_count,
            "--linux-x86_64-instance-type",
            e.linux_instance_type,
            # TODO: Confirm Possible options:
            #   --cluster-manager-instance-type, --service-host-instance-ebs-size, --service-host-instance-type
            "--cluster-manager-instance-type",
            e.service_instance_type,
        ]

        cmd.extend(e.rib_flags)

        if self.dry_run:
            print(" ".join(str(c) for c in cmd))
            return

        if self.aws_env.path().exists():
            raise PRTError(
                f"Environment {e.name} already exists. Please make sure it's downed and run prt aws_commands rm."
            )

        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument(
            "-n", "--dry-run", action="store_true", help="Don't create the environment, just print the RIB command."
        )
