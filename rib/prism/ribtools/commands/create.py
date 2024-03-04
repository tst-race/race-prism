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
from prism.ribtools.commands.configure import Configure
from prism.ribtools.commands.remove import Remove
from prism.ribtools.deployment import DeploymentMode
from prism.ribtools.environment import environment
from prism.ribtools.error import PRTError

from ..command import RIBCommand


class Create(RIBCommand):
    """Instruct RIB to create and configure the active deployment."""

    aliases = ["cr"]

    force: bool = False
    no_cache: bool = False
    dry_run: bool = False

    def pre_run(self):
        super().pre_run()

        d = self.ensure_current()
        if d.mode == DeploymentMode.aws:
            self.ensure_aws()

    def run(self):
        d = self.ensure_current()
        if d.path().exists():
            if not self.force and not self.dry_run:
                raise PRTError(f"Deployment {d.name} already exists. Use --force to recreate.")

            if not self.dry_run:
                Remove(name=d.name, purge=False).run()

        cmd = [
            *self.deployment_boilerplate(d, "create"),
            "--race",
            environment.race_version,
            "--network-manager-plugin",
            d.artifact,
            "--disable-config-encryption",
        ]

        if d.mode == DeploymentMode.aws:
            e = self.ensure_aws()
            cmd.extend(["--aws-env-name", e.name])

        for ch in d.comms_channels:
            cmd.extend(["--comms-channel", ch])
        if d.bootstrap_client_count + d.bootstrap_android_client_count:
            cmd.extend(["--comms-channel", "twoSixBootstrapCpp"])
        if self.no_cache:
            cmd.append("--cache=NEVER")

        if d.client_image:
            cmd.extend(["--linux-client-image", d.client_image])
        if d.server_image:
            cmd.extend(["--linux-server-image", d.server_image])
        if d.android_image:
            cmd.extend(["--android-client-image", d.android_image])
        else:
            cmd.extend(
                [
                    "--linux-server-count",
                    str(d.server_count),
                    "--linux-client-count",
                    str(d.client_count),
                    "--linux-client-uninstalled-count",
                    str(d.bootstrap_client_count),
                    "--android-client-count",
                    str(d.android_client_count),
                    "--android-client-uninstalled-count",
                    str(d.bootstrap_android_client_count),
                ]
            )

        cmd.extend(d.rib_flags)

        if d.custom_args:
            cmd.append("--no-config-gen")

        if self.dry_run:
            print(" ".join(cmd))
            if d.custom_args:
                Configure(verbose=self.verbose, dry_run=self.dry_run).run()
            return

        result = self.subprocess(cmd)
        self.fix_permissions()

        if result.returncode:
            raise PRTError("Error creating deployment.")

        # remove any prior start time
        environment.last_started.unlink(missing_ok=True)

        if d.custom_args:
            Configure(verbose=self.verbose).run()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument(
            "-f", "--force", action="store_true", help="If the deployment already exists, re-create it."
        )
        parser.add_argument("--no-cache", action="store_true", help="Don't use cached plugins.")
        parser.add_argument(
            "-n", "--dry-run", action="store_true", help="Don't create the deployment, just print the RIB command."
        )
